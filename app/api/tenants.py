import json
import secrets
from typing import Any, Optional
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from app.api.auth import get_current_actor
from app.api.problems import ProblemException
from app.db import get_connection, utc_now_iso
from app.domain.checklist import CATALOG_MODULES, build_checklist
from app.domain.policies import check_seat_cap
from app.domain.status import compute_derived_status

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])

ALLOWED_REGIONS = ["ap-south-1", "us-east-1", "eu-west-1"]

def generate_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"

def get_tenant_full(tenant_id: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,))
        t_row = cursor.fetchone()
        if not t_row:
            return None
        tenant = dict(t_row)

        cursor.execute("SELECT * FROM contracts WHERE id = ?", (tenant["contract_id"],))
        contract = dict(cursor.fetchone())

        cursor.execute("SELECT module FROM contract_modules WHERE contract_id = ?", (contract["id"],))
        c_modules = [r["module"] for r in cursor.fetchall()]

        cursor.execute("SELECT email, name FROM contract_admins WHERE contract_id = ?", (contract["id"],))
        c_admins = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT module FROM tenant_modules WHERE tenant_id = ?", (tenant_id,))
        t_modules = [r["module"] for r in cursor.fetchall()]

        cursor.execute("SELECT email, name FROM invites WHERE tenant_id = ? ORDER BY email ASC", (tenant_id,))
        t_invites = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT code, title, status FROM tasks WHERE tenant_id = ? ORDER BY created_at ASC", (tenant_id,))
        t_tasks = [dict(r) for r in cursor.fetchall()]

    # Ordered modules
    ordered_t_modules = [m for m in CATALOG_MODULES if m in set(t_modules)]

    # Checklist
    c_admin_emails = [a["email"] for a in c_admins]
    t_invite_emails = [i["email"] for i in t_invites]

    checklist = build_checklist(
        contract_region=contract["region"],
        tenant_region=tenant["region"],
        contract_modules=c_modules,
        tenant_modules=t_modules,
        contract_admin_emails=c_admin_emails,
        tenant_admin_emails=t_invite_emails,
        sso_required=bool(contract["sso_required"]),
        sso_metadata_present=bool(contract["sso_metadata_present"]),
        live_at=tenant["live_at"],
    )

    has_open_tasks = any(task["status"] == "open" for task in t_tasks)

    status = compute_derived_status(
        live_at=tenant["live_at"],
        region_matches=checklist["region"]["ok"],
        modules_match=checklist["modules"]["ok"],
        admins_match=checklist["admins"]["ok"],
        sso_required=bool(contract["sso_required"]),
        sso_metadata_present=bool(contract["sso_metadata_present"]),
        has_open_tasks=has_open_tasks,
    )

    return {
        "tenantId": tenant["id"],
        "contractId": tenant["contract_id"],
        "customerName": tenant["customer_name"],
        "seats": tenant["seats"],
        "region": tenant["region"],
        "status": status,
        "live": bool(tenant["live_at"]),
        "modules": ordered_t_modules,
        "invites": t_invites,
        "tasks": t_tasks,
        "checklist": checklist,
    }

async def read_json_body(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except Exception:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="Request body must be a valid JSON object",
        )

@router.post("", status_code=201)
async def create_tenant(
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    actor: str = Depends(get_current_actor),
):
    if not idempotency_key:
        raise ProblemException(
            status=400,
            code="IDEMPOTENCY_KEY_MISSING",
            title="Idempotency key missing",
            detail="Header 'Idempotency-Key' is required",
        )

    body = await read_json_body(request)
    unknown = set(body.keys()) - {"contractId"}
    if unknown or "contractId" not in body:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail=f"Invalid body fields: expected only 'contractId'",
        )

    contract_id = body["contractId"]
    if not isinstance(contract_id, str):
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="contractId must be a string",
        )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,))
        contract = cursor.fetchone()
        if not contract:
            raise ProblemException(
                status=404,
                code="CONTRACT_NOT_FOUND",
                title="Contract not found",
                detail=f"Contract '{contract_id}' does not exist",
            )

        # Check if contract already has a tenant
        cursor.execute("SELECT * FROM tenants WHERE contract_id = ?", (contract_id,))
        existing_for_contract = cursor.fetchone()
        if existing_for_contract:
            if existing_for_contract["idempotency_key"] == idempotency_key:
                # Replay
                tenant_full = get_tenant_full(existing_for_contract["id"])
                resp_data = {
                    "tenantId": tenant_full["tenantId"],
                    "contractId": tenant_full["contractId"],
                    "customerName": tenant_full["customerName"],
                    "seats": tenant_full["seats"],
                    "region": tenant_full["region"],
                    "status": tenant_full["status"],
                    "live": tenant_full["live"],
                }
                return JSONResponse(status_code=200, content=resp_data, headers={"Idempotent-Replayed": "true"})
            else:
                raise ProblemException(
                    status=409,
                    code="CONTRACT_ALREADY_PROVISIONED",
                    title="Contract already provisioned",
                    detail=f"Contract '{contract_id}' already has a tenant with a different idempotency key",
                )

        # Check if idempotency key was used for a different contract
        cursor.execute("SELECT * FROM tenants WHERE idempotency_key = ?", (idempotency_key,))
        existing_key = cursor.fetchone()
        if existing_key:
            raise ProblemException(
                status=409,
                code="IDEMPOTENCY_KEY_REUSED",
                title="Idempotency key reused",
                detail=f"Idempotency key '{idempotency_key}' already used for another contract",
            )

        tenant_id = generate_id("ten")
        now = utc_now_iso()
        cursor.execute(
            """
            INSERT INTO tenants (id, contract_id, idempotency_key, customer_name, seats, region, live_at, created_at)
            VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)
            """,
            (
                tenant_id,
                contract_id,
                idempotency_key,
                contract["customer_name"],
                contract["seats"],
                now,
            ),
        )
        conn.commit()

    resp_data = {
        "tenantId": tenant_id,
        "contractId": contract_id,
        "customerName": contract["customer_name"],
        "seats": contract["seats"],
        "region": None,
        "status": "provisioning",
        "live": False,
    }
    return JSONResponse(status_code=201, content=resp_data)

@router.post("/{tenantId}/region")
async def set_region(
    tenantId: str,
    request: Request,
    actor: str = Depends(get_current_actor),
):
    body = await read_json_body(request)
    unknown = set(body.keys()) - {"region"}
    if unknown or "region" not in body or not isinstance(body["region"], str):
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="Body must only contain 'region' string",
        )

    region = body["region"]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenantId,))
        tenant = cursor.fetchone()
        if not tenant:
            raise ProblemException(
                status=404,
                code="TENANT_NOT_FOUND",
                title="Tenant not found",
                detail=f"Tenant '{tenantId}' does not exist",
            )

        if tenant["live_at"] is not None:
            raise ProblemException(
                status=409,
                code="ALREADY_LIVE",
                title="Already live",
                detail="Tenant is already live and cannot be modified",
            )

        if region not in ALLOWED_REGIONS:
            raise ProblemException(
                status=422,
                code="UNKNOWN_REGION",
                title="Unknown region",
                detail=f"Region '{region}' is not in allowed catalog",
            )

        cursor.execute("SELECT region FROM contracts WHERE id = ?", (tenant["contract_id"],))
        contract_region = cursor.fetchone()["region"]

        if tenant["region"] is not None:
            if tenant["region"] == region:
                tenant_full = get_tenant_full(tenantId)
                return JSONResponse(status_code=200, content=tenant_full, headers={"Idempotent-Replayed": "true"})
            else:
                raise ProblemException(
                    status=409,
                    code="REGION_ALREADY_SET",
                    title="Region already set",
                    detail=f"Tenant already has region '{tenant['region']}' set",
                )

        if region != contract_region:
            raise ProblemException(
                status=422,
                code="REGION_MISMATCH",
                title="Region mismatch",
                detail=f"Region '{region}' does not match contracted region '{contract_region}'",
            )

        cursor.execute("UPDATE tenants SET region = ? WHERE id = ?", (region, tenantId))
        conn.commit()

    tenant_full = get_tenant_full(tenantId)
    return JSONResponse(status_code=200, content=tenant_full)

@router.post("/{tenantId}/modules")
async def enable_module(
    tenantId: str,
    request: Request,
    actor: str = Depends(get_current_actor),
):
    body = await read_json_body(request)
    unknown = set(body.keys()) - {"module"}
    if unknown or "module" not in body or not isinstance(body["module"], str):
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="Body must only contain 'module' string",
        )

    module = body["module"]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenantId,))
        tenant = cursor.fetchone()
        if not tenant:
            raise ProblemException(
                status=404,
                code="TENANT_NOT_FOUND",
                title="Tenant not found",
                detail=f"Tenant '{tenantId}' does not exist",
            )

        if tenant["live_at"] is not None:
            raise ProblemException(
                status=409,
                code="ALREADY_LIVE",
                title="Already live",
                detail="Tenant is already live and cannot be modified",
            )

        if module not in CATALOG_MODULES:
            raise ProblemException(
                status=422,
                code="UNKNOWN_MODULE",
                title="Unknown module",
                detail=f"Module '{module}' is not in catalog",
            )

        cursor.execute(
            "SELECT 1 FROM contract_modules WHERE contract_id = ? AND module = ?",
            (tenant["contract_id"], module),
        )
        if not cursor.fetchone():
            raise ProblemException(
                status=422,
                code="MODULE_NOT_PURCHASED",
                title="Module not purchased",
                detail=f"Module '{module}' is not on contract {tenant['contract_id']}",
            )

        cursor.execute(
            "SELECT 1 FROM tenant_modules WHERE tenant_id = ? AND module = ?",
            (tenantId, module),
        )
        already_enabled = cursor.fetchone() is not None

        if not already_enabled:
            cursor.execute(
                "INSERT INTO tenant_modules (tenant_id, module, enabled_at) VALUES (?, ?, ?)",
                (tenantId, module, utc_now_iso()),
            )
            conn.commit()

        cursor.execute("SELECT module FROM tenant_modules WHERE tenant_id = ?", (tenantId,))
        enabled_modules = [r["module"] for r in cursor.fetchall()]
        ordered = [m for m in CATALOG_MODULES if m in set(enabled_modules)]

        headers = {"Idempotent-Replayed": "true"} if already_enabled else {}
        return JSONResponse(status_code=200, content=ordered, headers=headers)

@router.post("/{tenantId}/invites")
async def invite_admin(
    tenantId: str,
    request: Request,
    actor: str = Depends(get_current_actor),
):
    body = await read_json_body(request)
    unknown = set(body.keys()) - {"email"}
    if unknown or "email" not in body or not isinstance(body["email"], str):
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="Body must only contain 'email' string",
        )

    email = body["email"].strip().lower()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenantId,))
        tenant = cursor.fetchone()
        if not tenant:
            raise ProblemException(
                status=404,
                code="TENANT_NOT_FOUND",
                title="Tenant not found",
                detail=f"Tenant '{tenantId}' does not exist",
            )

        if tenant["live_at"] is not None:
            raise ProblemException(
                status=409,
                code="ALREADY_LIVE",
                title="Already live",
                detail="Tenant is already live and cannot be modified",
            )

        cursor.execute(
            "SELECT name FROM contract_admins WHERE contract_id = ? AND email = ?",
            (tenant["contract_id"], email),
        )
        contract_admin = cursor.fetchone()
        if not contract_admin:
            raise ProblemException(
                status=422,
                code="EMAIL_NOT_ON_CONTRACT",
                title="Email not on contract",
                detail=f"Email '{email}' is not a designated admin on contract {tenant['contract_id']}",
            )

        cursor.execute(
            "SELECT * FROM invites WHERE tenant_id = ? AND email = ?",
            (tenantId, email),
        )
        existing_invite = cursor.fetchone()
        if existing_invite:
            return JSONResponse(
                status_code=200,
                content={"email": existing_invite["email"], "name": existing_invite["name"]},
                headers={"Idempotent-Replayed": "true"},
            )

        cursor.execute("SELECT COUNT(DISTINCT email) as cnt FROM invites WHERE tenant_id = ?", (tenantId,))
        current_count = cursor.fetchone()["cnt"]

        check_seat_cap(
            seats=tenant["seats"],
            current_invite_count=current_count,
            is_already_invited=False,
        )

        invite_id = generate_id("inv")
        name = contract_admin["name"]
        cursor.execute(
            "INSERT INTO invites (id, tenant_id, email, name, created_at) VALUES (?, ?, ?, ?, ?)",
            (invite_id, tenantId, email, name, utc_now_iso()),
        )
        conn.commit()

    return JSONResponse(status_code=200, content={"email": email, "name": name})

@router.post("/{tenantId}/tasks")
async def create_task(
    tenantId: str,
    request: Request,
    actor: str = Depends(get_current_actor),
):
    body = await read_json_body(request)
    unknown = set(body.keys()) - {"code"}
    if unknown or "code" not in body or not isinstance(body["code"], str):
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="Body must only contain 'code' string",
        )

    code = body["code"]
    if code != "collect_sso_metadata":
        raise ProblemException(
            status=422,
            code="TASK_NOT_APPLICABLE",
            title="Task not applicable",
            detail=f"Task code '{code}' is not supported",
        )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenantId,))
        tenant = cursor.fetchone()
        if not tenant:
            raise ProblemException(
                status=404,
                code="TENANT_NOT_FOUND",
                title="Tenant not found",
                detail=f"Tenant '{tenantId}' does not exist",
            )

        if tenant["live_at"] is not None:
            raise ProblemException(
                status=409,
                code="ALREADY_LIVE",
                title="Already live",
                detail="Tenant is already live and cannot be modified",
            )

        cursor.execute("SELECT sso_required, sso_metadata_present FROM contracts WHERE id = ?", (tenant["contract_id"],))
        contract = cursor.fetchone()
        if not contract["sso_required"] or contract["sso_metadata_present"]:
            raise ProblemException(
                status=422,
                code="TASK_NOT_APPLICABLE",
                title="Task not applicable",
                detail="SSO metadata is not required or has already been collected",
            )

        cursor.execute("SELECT * FROM tasks WHERE tenant_id = ? AND code = ?", (tenantId, code))
        existing_task = cursor.fetchone()
        if existing_task:
            return JSONResponse(
                status_code=200,
                content={
                    "code": existing_task["code"],
                    "title": existing_task["title"],
                    "status": existing_task["status"],
                },
                headers={"Idempotent-Replayed": "true"},
            )

        task_id = generate_id("tsk")
        title = "Collect SSO metadata from the customer"
        status = "open"
        cursor.execute(
            "INSERT INTO tasks (id, tenant_id, code, title, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, tenantId, code, title, status, utc_now_iso()),
        )
        conn.commit()

    return JSONResponse(status_code=200, content={"code": code, "title": title, "status": status})

@router.get("/{tenantId}")
async def get_tenant(
    tenantId: str,
    actor: str = Depends(get_current_actor),
):
    tenant_full = get_tenant_full(tenantId)
    if not tenant_full:
        raise ProblemException(
            status=404,
            code="TENANT_NOT_FOUND",
            title="Tenant not found",
            detail=f"Tenant '{tenantId}' does not exist",
        )
    return JSONResponse(status_code=200, content=tenant_full)

@router.post("/{tenantId}/sso-metadata")
async def record_sso_metadata(
    tenantId: str,
    request: Request,
    actor: str = Depends(get_current_actor),
):
    if actor != "operator":
        raise ProblemException(
            status=403,
            code="AGENT_FORBIDDEN",
            title="Agent forbidden",
            detail="Agent role cannot record SSO metadata",
        )

    body = await read_json_body(request)
    if body:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="Body must be an empty object",
        )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenantId,))
        tenant = cursor.fetchone()
        if not tenant:
            raise ProblemException(
                status=404,
                code="TENANT_NOT_FOUND",
                title="Tenant not found",
                detail=f"Tenant '{tenantId}' does not exist",
            )

        cursor.execute("SELECT sso_required, sso_metadata_present FROM contracts WHERE id = ?", (tenant["contract_id"],))
        contract = cursor.fetchone()
        if not contract["sso_required"]:
            raise ProblemException(
                status=422,
                code="TASK_NOT_APPLICABLE",
                title="Task not applicable",
                detail="SSO is not required for this contract",
            )

        if contract["sso_metadata_present"]:
            tenant_full = get_tenant_full(tenantId)
            return JSONResponse(status_code=200, content=tenant_full, headers={"Idempotent-Replayed": "true"})

        cursor.execute("UPDATE contracts SET sso_metadata_present = 1 WHERE id = ?", (tenant["contract_id"],))

        cursor.execute("SELECT id FROM tasks WHERE tenant_id = ? AND code = 'collect_sso_metadata'", (tenantId,))
        existing_task = cursor.fetchone()
        if existing_task:
            cursor.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (existing_task["id"],))
        else:
            task_id = generate_id("tsk")
            cursor.execute(
                """
                INSERT INTO tasks (id, tenant_id, code, title, status, created_at)
                VALUES (?, ?, 'collect_sso_metadata', 'Collect SSO metadata from the customer', 'done', ?)
                """,
                (task_id, tenantId, utc_now_iso()),
            )
        conn.commit()

    tenant_full = get_tenant_full(tenantId)
    return JSONResponse(status_code=200, content=tenant_full)

@router.post("/{tenantId}/go-live")
async def go_live(
    tenantId: str,
    request: Request,
    actor: str = Depends(get_current_actor),
):
    if actor != "operator":
        raise ProblemException(
            status=403,
            code="AGENT_FORBIDDEN",
            title="Agent forbidden",
            detail="Agent role cannot mark account live",
        )

    body = await read_json_body(request)
    if body:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="Body must be an empty object",
        )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenantId,))
        tenant = cursor.fetchone()
        if not tenant:
            raise ProblemException(
                status=404,
                code="TENANT_NOT_FOUND",
                title="Tenant not found",
                detail=f"Tenant '{tenantId}' does not exist",
            )

        # Precondition Refusal Order:
        # 1. 409 ALREADY_LIVE if live_at is set
        if tenant["live_at"] is not None:
            raise ProblemException(
                status=409,
                code="ALREADY_LIVE",
                title="Already live",
                detail="Tenant is already live",
            )

        tenant_full = get_tenant_full(tenantId)
        checklist = tenant_full["checklist"]

        # 2. 409 CHECKLIST_INCOMPLETE if region, modules, or admins do not match
        if not (checklist["region"]["ok"] and checklist["modules"]["ok"] and checklist["admins"]["ok"]):
            raise ProblemException(
                status=409,
                code="CHECKLIST_INCOMPLETE",
                title="Checklist incomplete",
                detail="Tenant configuration does not match the contract",
            )

        # 3. 409 SSO_NOT_READY if SSO is required and metadata is absent
        if not checklist["sso"]["ok"]:
            raise ProblemException(
                status=409,
                code="SSO_NOT_READY",
                title="SSO not ready",
                detail="SSO metadata is required but has not been recorded",
            )

        # 4. 409 CHECKLIST_INCOMPLETE if any task is still open after SSO is satisfied
        cursor.execute("SELECT 1 FROM tasks WHERE tenant_id = ? AND status = 'open'", (tenantId,))
        if cursor.fetchone():
            raise ProblemException(
                status=409,
                code="CHECKLIST_INCOMPLETE",
                title="Checklist incomplete",
                detail="Tenant still has open tasks",
            )

        now = utc_now_iso()
        cursor.execute("UPDATE tenants SET live_at = ? WHERE id = ?", (now, tenantId))
        conn.commit()

    tenant_full = get_tenant_full(tenantId)
    return JSONResponse(status_code=200, content=tenant_full)


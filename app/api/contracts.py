import json
import os
import re
from typing import Any, Optional
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from app.api.auth import get_current_actor
from app.api.problems import ProblemException, problem_response
from app.db import get_connection, utc_now_iso

router = APIRouter(prefix="/api/v1/contracts", tags=["contracts"])

CATALOG_MODULES = ["projects", "time", "billing"]
ALLOWED_REGIONS = ["ap-south-1", "us-east-1", "eu-west-1"]
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTRACT_ID_REGEX = re.compile(r"^ctr_[a-z]+$")

ALLOWED_CONTRACT_FIELDS = {
    "contractId",
    "customerName",
    "seats",
    "modules",
    "region",
    "admins",
    "ssoRequired",
    "ssoMetadataPresent",
}

ALLOWED_ADMIN_FIELDS = {"name", "email"}

def validate_contract_payload(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="Contract payload must be a JSON object",
        )

    # Check for unknown fields
    unknown_fields = set(body.keys()) - ALLOWED_CONTRACT_FIELDS
    if unknown_fields:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail=f"Unknown fields in contract payload: {', '.join(sorted(unknown_fields))}",
        )

    # Check for missing required fields
    missing_fields = ALLOWED_CONTRACT_FIELDS - set(body.keys())
    if missing_fields:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail=f"Missing required fields: {', '.join(sorted(missing_fields))}",
        )

    contract_id = body["contractId"]
    if not isinstance(contract_id, str) or not CONTRACT_ID_REGEX.match(contract_id):
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="contractId must match 'ctr_' followed by lowercase letters",
        )

    customer_name = body["customerName"]
    if not isinstance(customer_name, str) or not customer_name.strip():
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="customerName must be a non-empty string",
        )

    seats = body["seats"]
    if not isinstance(seats, int) or isinstance(seats, bool) or seats < 1 or seats > 100000:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="seats must be an integer between 1 and 100000",
        )

    modules = body["modules"]
    if not isinstance(modules, list) or len(modules) == 0:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="modules must be a non-empty list",
        )
    if len(modules) != len(set(modules)):
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="modules must not contain duplicates",
        )
    for mod in modules:
        if not isinstance(mod, str) or mod not in CATALOG_MODULES:
            raise ProblemException(
                status=422,
                code="UNKNOWN_MODULE",
                title="Unknown module",
                detail=f"Module '{mod}' is not in catalog",
            )

    region = body["region"]
    if not isinstance(region, str) or region not in ALLOWED_REGIONS:
        raise ProblemException(
            status=422,
            code="UNKNOWN_REGION",
            title="Unknown region",
            detail=f"Region '{region}' is not allowed",
        )

    admins = body["admins"]
    if not isinstance(admins, list) or len(admins) == 0:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="admins must be a non-empty list",
        )
    if len(admins) > seats:
        raise ProblemException(
            status=422,
            code="CONTRACT_SEAT_CONFLICT",
            title="Contract seat conflict",
            detail=f"Admin count ({len(admins)}) exceeds purchased seats ({seats})",
        )

    seen_emails = set()
    cleaned_admins = []
    for admin in admins:
        if not isinstance(admin, dict):
            raise ProblemException(
                status=422,
                code="VALIDATION_ERROR",
                title="Validation error",
                detail="Each admin must be an object",
            )
        admin_unknown = set(admin.keys()) - ALLOWED_ADMIN_FIELDS
        if admin_unknown:
            raise ProblemException(
                status=422,
                code="VALIDATION_ERROR",
                title="Validation error",
                detail=f"Unknown admin fields: {', '.join(sorted(admin_unknown))}",
            )
        admin_missing = ALLOWED_ADMIN_FIELDS - set(admin.keys())
        if admin_missing:
            raise ProblemException(
                status=422,
                code="VALIDATION_ERROR",
                title="Validation error",
                detail=f"Missing admin fields: {', '.join(sorted(admin_missing))}",
            )
        email = admin["email"]
        name = admin["name"]
        if not isinstance(email, str) or not EMAIL_REGEX.match(email):
            raise ProblemException(
                status=422,
                code="VALIDATION_ERROR",
                title="Validation error",
                detail=f"Invalid admin email '{email}'",
            )
        if not isinstance(name, str) or not name.strip():
            raise ProblemException(
                status=422,
                code="VALIDATION_ERROR",
                title="Validation error",
                detail="Admin name must be a non-empty string",
            )
        lower_email = email.lower()
        if lower_email in seen_emails:
            raise ProblemException(
                status=422,
                code="VALIDATION_ERROR",
                title="Validation error",
                detail=f"Duplicate admin email '{lower_email}'",
            )
        seen_emails.add(lower_email)
        cleaned_admins.append({"name": name.strip(), "email": lower_email})

    sso_required = body["ssoRequired"]
    if not isinstance(sso_required, bool):
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="ssoRequired must be a boolean",
        )

    sso_metadata_present = body["ssoMetadataPresent"]
    if not isinstance(sso_metadata_present, bool):
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="ssoMetadataPresent must be a boolean",
        )

    # If ssoRequired is false, ssoMetadataPresent is stored false
    if not sso_required:
        sso_metadata_present = False

    return {
        "contractId": contract_id,
        "customerName": customer_name.strip(),
        "seats": seats,
        "modules": modules,
        "region": region,
        "admins": cleaned_admins,
        "ssoRequired": sso_required,
        "ssoMetadataPresent": sso_metadata_present,
    }

def format_stored_contract(contract_row: dict, module_rows: list[dict], admin_rows: list[dict]) -> dict[str, Any]:
    # Modules in catalog order
    modules_present = {row["module"] for row in module_rows}
    ordered_modules = [m for m in CATALOG_MODULES if m in modules_present]

    # Admins sorted by email
    sorted_admins = sorted(
        [{"name": row["name"], "email": row["email"]} for row in admin_rows],
        key=lambda a: a["email"],
    )

    return {
        "contractId": contract_row["id"],
        "customerName": contract_row["customer_name"],
        "seats": contract_row["seats"],
        "modules": ordered_modules,
        "region": contract_row["region"],
        "admins": sorted_admins,
        "ssoRequired": bool(contract_row["sso_required"]),
        "ssoMetadataPresent": bool(contract_row["sso_metadata_present"]),
    }

def fetch_contract(contract_id: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,))
        c_row = cursor.fetchone()
        if not c_row:
            return None
        cursor.execute("SELECT module FROM contract_modules WHERE contract_id = ?", (contract_id,))
        m_rows = cursor.fetchall()
        cursor.execute("SELECT name, email FROM contract_admins WHERE contract_id = ?", (contract_id,))
        a_rows = cursor.fetchall()
        return format_stored_contract(dict(c_row), [dict(r) for r in m_rows], [dict(r) for r in a_rows])

@router.post("", status_code=201)
async def create_contract(request: Request, actor: str = Depends(get_current_actor)):
    try:
        raw_body = await request.json()
    except Exception:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="Request body is not valid JSON",
        )

    validated = validate_contract_payload(raw_body)
    contract_id = validated["contractId"]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,))
        existing = cursor.fetchone()

        if existing:
            # Check if identical to existing
            cursor.execute("SELECT module FROM contract_modules WHERE contract_id = ?", (contract_id,))
            m_rows = cursor.fetchall()
            cursor.execute("SELECT name, email FROM contract_admins WHERE contract_id = ?", (contract_id,))
            a_rows = cursor.fetchall()
            existing_data = format_stored_contract(dict(existing), [dict(r) for r in m_rows], [dict(r) for r in a_rows])

            # Prepare canonical comparison
            candidate_modules = [m for m in CATALOG_MODULES if m in validated["modules"]]
            candidate_admins = sorted(validated["admins"], key=lambda a: a["email"])
            candidate_data = {
                "contractId": validated["contractId"],
                "customerName": validated["customerName"],
                "seats": validated["seats"],
                "modules": candidate_modules,
                "region": validated["region"],
                "admins": candidate_admins,
                "ssoRequired": validated["ssoRequired"],
                "ssoMetadataPresent": validated["ssoMetadataPresent"],
            }

            if existing_data == candidate_data:
                return JSONResponse(
                    status_code=200,
                    content=existing_data,
                    headers={"Idempotent-Replayed": "true"},
                )
            else:
                raise ProblemException(
                    status=409,
                    code="IDEMPOTENCY_KEY_REUSED",
                    title="Idempotency key reused",
                    detail=f"Contract '{contract_id}' already exists with different data",
                )

        # Insert new contract transactionally
        now = utc_now_iso()
        cursor.execute(
            """
            INSERT INTO contracts (id, customer_name, seats, region, sso_required, sso_metadata_present, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                validated["contractId"],
                validated["customerName"],
                validated["seats"],
                validated["region"],
                1 if validated["ssoRequired"] else 0,
                1 if validated["ssoMetadataPresent"] else 0,
                now,
            ),
        )
        for mod in validated["modules"]:
            cursor.execute(
                "INSERT INTO contract_modules (contract_id, module) VALUES (?, ?)",
                (contract_id, mod),
            )
        for admin in validated["admins"]:
            cursor.execute(
                "INSERT INTO contract_admins (contract_id, email, name) VALUES (?, ?, ?)",
                (contract_id, admin["email"], admin["name"]),
            )
        conn.commit()

    stored = fetch_contract(contract_id)
    return JSONResponse(status_code=201, content=stored)

@router.get("/{contractId}")
async def get_contract(contractId: str, actor: str = Depends(get_current_actor)):
    stored = fetch_contract(contractId)
    if not stored:
        raise ProblemException(
            status=404,
            code="CONTRACT_NOT_FOUND",
            title="Contract not found",
            detail=f"Contract '{contractId}' does not exist",
        )
    return JSONResponse(status_code=200, content=stored)


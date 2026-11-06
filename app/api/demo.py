import json
import os
from pathlib import Path
from typing import Any, Optional
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import httpx
from app.agent.fake_model import FakeModel
from app.agent.live_model import LiveModel
from app.agent.loop import AgentRunResult, run_agent_loop
from app.api.auth import get_env_tokens
from app.api.contracts import fetch_contract, validate_contract_payload
from app.api.problems import ProblemException
from app.api.tenants import get_tenant_full
from app.db import get_connection, utc_now_iso

router = APIRouter(prefix="/api/demo", tags=["demo"])

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"

def load_scenarios() -> dict[str, dict[str, Any]]:
    with open(FIXTURES_DIR / "scenarios.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return {s["id"]: s for s in data["scenarios"]}

def ensure_contract_stored(contract_file: str) -> dict[str, Any]:
    with open(FIXTURES_DIR / contract_file, "r", encoding="utf-8") as f:
        contract_data = json.load(f)

    validated = validate_contract_payload(contract_data)
    contract_id = validated["contractId"]

    existing = fetch_contract(contract_id)
    if existing:
        return existing

    with get_connection() as conn:
        cursor = conn.cursor()
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
                utc_now_iso(),
            ),
        )
        for mod in validated["modules"]:
            cursor.execute("INSERT INTO contract_modules (contract_id, module) VALUES (?, ?)", (contract_id, mod))
        for admin in validated["admins"]:
            cursor.execute(
                "INSERT INTO contract_admins (contract_id, email, name) VALUES (?, ?, ?)",
                (contract_id, admin["email"], admin["name"]),
            )
        conn.commit()

    return fetch_contract(contract_id)

class DatabaseRunRecorder:
    def on_run_start(
        self,
        run_id: str,
        scenario: str,
        contract_id: str,
        mode: str,
        idempotency_key: str,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, scenario, contract_id, mode, idempotency_key, stopped_reason, final_text, created_at)
                VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)
                """,
                (run_id, scenario, contract_id, mode, idempotency_key, utc_now_iso()),
            )
            conn.commit()

    def on_step_complete(
        self,
        run_id: str,
        step_index: int,
        tool_name: str,
        arguments_json: str,
        http_status: int,
        error_code: Optional[str],
        result_json: str,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO run_steps (run_id, step_index, tool_name, arguments_json, http_status, error_code, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, step_index, tool_name, arguments_json, http_status, error_code, result_json),
            )
            conn.commit()

    def on_run_finish(
        self,
        run_id: str,
        stopped_reason: str,
        final_text: str,
        token_usage: Optional[int] = None,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE runs SET stopped_reason = ?, final_text = ?, token_usage = ? WHERE id = ?",
                (stopped_reason, final_text, token_usage, run_id),
            )
            conn.commit()

@router.post("/run")
async def run_demo(request: Request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError()
    except Exception:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="Request body must be a JSON object",
        )

    unknown = set(body.keys()) - {"scenario", "mode"}
    if unknown or "scenario" not in body or "mode" not in body:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="Body must contain 'scenario' and 'mode'",
        )

    scenario_name = body["scenario"]
    mode = body["mode"]

    if mode == "live":
        llm_base_url = os.environ.get("LLM_BASE_URL")
        llm_api_key = os.environ.get("LLM_API_KEY")
        llm_model_name = os.environ.get("LLM_MODEL")
        if not llm_base_url or not llm_api_key or not llm_model_name:
            raise ProblemException(
                status=400,
                code="LIVE_MODEL_NOT_CONFIGURED",
                title="Live model not configured",
                detail="Live mode requires LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL",
            )
    elif mode != "fake":
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail=f"Unsupported mode '{mode}'",
        )

    scenarios = load_scenarios()
    if scenario_name not in scenarios:
        raise ProblemException(
            status=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail=f"Unknown scenario '{scenario_name}'",
        )

    scenario_config = scenarios[scenario_name]

    # If scenario is northwind_retry and no Northwind tenant exists yet, return 409 VALIDATION_ERROR
    if scenario_name == "northwind_retry":
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tenants WHERE contract_id = 'ctr_northwind'")
            if not cursor.fetchone():
                raise ProblemException(
                    status=409,
                    code="VALIDATION_ERROR",
                    title="Validation error",
                    detail="Scenario 'northwind' must be run before 'northwind_retry'",
                )

    stored_contract = ensure_contract_stored(scenario_config["contractFile"])

    base_url = str(request.base_url).rstrip("/")
    _, agent_token, _ = get_env_tokens()

    if mode == "fake":
        model_instance = FakeModel(scenario=scenario_name, contract_id=scenario_config["contractId"])
    else:
        model_instance = LiveModel(
            base_url=llm_base_url,
            api_key=llm_api_key,
            model=llm_model_name,
            scenario=scenario_name,
            contract_id=scenario_config["contractId"],
            idempotency_key=scenario_config["idempotencyKey"],
            scenario_message=scenario_config["message"],
        )

    recorder = DatabaseRunRecorder()

    import asyncio
    run_result: AgentRunResult = await asyncio.to_thread(
        run_agent_loop,
        scenario=scenario_name,
        contract_id=scenario_config["contractId"],
        idempotency_key=scenario_config["idempotencyKey"],
        mode=mode,
        base_url=base_url,
        agent_token=agent_token,
        model=model_instance,
        recorder=recorder,
    )



    # Fetch final tenant
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tenants WHERE contract_id = ?", (scenario_config["contractId"],))
        t_row = cursor.fetchone()
        tenant_full = get_tenant_full(t_row["id"]) if t_row else None

    steps_resp = [
        {
            "stepIndex": s.step_index,
            "toolName": s.tool_name,
            "httpStatus": s.http_status,
            "errorCode": s.error_code,
            "replayed": s.replayed,
            "arguments": s.arguments,
        }
        for s in run_result.steps
    ]

    return JSONResponse(
        status_code=200,
        content={
            "runId": run_result.run_id,
            "stoppedReason": run_result.stopped_reason,
            "message": scenario_config["message"],
            "contract": stored_contract,
            "tenant": tenant_full,
            "steps": steps_resp,
        },
    )

@router.post("/tenants/{tenantId}/sso-metadata")
async def demo_sso_metadata(tenantId: str, request: Request):
    base_url = str(request.base_url).rstrip("/")
    _, _, operator_token = get_env_tokens()
    headers = {"Authorization": f"Bearer {operator_token}"}

    async with httpx.AsyncClient(base_url=base_url) as client:
        resp = await client.post(f"/api/v1/tenants/{tenantId}/sso-metadata", json={}, headers=headers)
        return JSONResponse(status_code=resp.status_code, content=resp.json())

@router.post("/tenants/{tenantId}/go-live")
async def demo_go_live(tenantId: str, request: Request):
    base_url = str(request.base_url).rstrip("/")
    _, _, operator_token = get_env_tokens()
    headers = {"Authorization": f"Bearer {operator_token}"}

    async with httpx.AsyncClient(base_url=base_url) as client:
        resp = await client.post(f"/api/v1/tenants/{tenantId}/go-live", json={}, headers=headers)
        return JSONResponse(status_code=resp.status_code, content=resp.json())

@router.get("/runs/{runId}")
async def get_demo_run(runId: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM runs WHERE id = ?", (runId,))
        r_row = cursor.fetchone()
        if not r_row:
            raise ProblemException(
                status=404,
                code="RUN_NOT_FOUND",
                title="Run not found",
                detail=f"Run '{runId}' not found",
            )
        run_data = dict(r_row)

        cursor.execute("SELECT * FROM run_steps WHERE run_id = ? ORDER BY step_index ASC", (runId,))
        step_rows = [dict(s) for s in cursor.fetchall()]

        cursor.execute("SELECT id FROM tenants WHERE contract_id = ?", (run_data["contract_id"],))
        t_row = cursor.fetchone()
        tenant = get_tenant_full(t_row["id"]) if t_row else None

    steps = [
        {
            "stepIndex": s["step_index"],
            "toolName": s["tool_name"],
            "httpStatus": s["http_status"],
            "errorCode": s["error_code"],
            "arguments": json.loads(s["arguments_json"]),
            "result": json.loads(s["result_json"]) if s["result_json"] else None,
        }
        for s in step_rows
    ]

    return JSONResponse(
        status_code=200,
        content={
            "run": run_data,
            "steps": steps,
            "tenant": tenant,
        },
    )

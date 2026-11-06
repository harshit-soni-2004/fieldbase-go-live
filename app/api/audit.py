import json
import secrets
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.api.auth import get_env_tokens
from app.db import get_connection, utc_now_iso

def generate_audit_id() -> str:
    return f"aud_{secrets.token_hex(6)}"

def log_audit_event(
    run_id: Optional[str],
    actor: str,
    method: str,
    path: str,
    http_status: int,
    error_code: Optional[str],
    request_json: str,
    response_json: str,
) -> None:
    event_id = generate_audit_id()
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_events (
                id, run_id, actor, method, path, http_status, error_code,
                request_json, response_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                run_id,
                actor,
                method,
                path,
                http_status,
                error_code,
                request_json,
                response_json,
                now,
            ),
        )
        conn.commit()

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only audit admin API calls (/api/v1/...)
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)

        run_id = request.headers.get("X-Run-Id")
        auth_header = request.headers.get("Authorization", "")
        _, agent_token, operator_token = get_env_tokens()

        token = auth_header[len("Bearer "):].strip() if auth_header.startswith("Bearer ") else ""
        if token == agent_token:
            actor = "agent"
        elif token == operator_token:
            actor = "operator"
        else:
            actor = "unknown"

        # Cache request body
        req_bytes = await request.body()
        req_str = req_bytes.decode("utf-8") if req_bytes else "{}"
        try:
            # Ensure valid JSON formatting if possible
            req_json = json.dumps(json.loads(req_str))
        except Exception:
            req_json = req_str

        # Call the endpoint
        response = await call_next(request)

        # Intercept response body
        resp_body = [section async for section in response.body_iterator]
        resp_bytes = b"".join(resp_body)
        resp_str = resp_bytes.decode("utf-8") if resp_bytes else ""

        error_code = None
        try:
            parsed_resp = json.loads(resp_str)
            if isinstance(parsed_resp, dict) and "code" in parsed_resp:
                error_code = parsed_resp["code"]
            resp_json = json.dumps(parsed_resp)
        except Exception:
            resp_json = resp_str

        try:
            log_audit_event(
                run_id=run_id,
                actor=actor,
                method=request.method,
                path=request.url.path,
                http_status=response.status_code,
                error_code=error_code,
                request_json=req_json,
                response_json=resp_json,
            )
        except Exception:
            pass  # Do not fail request if audit logging fails

        return Response(
            content=resp_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )


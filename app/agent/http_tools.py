import json
from dataclasses import dataclass
from typing import Any, Optional
import httpx

@dataclass
class ToolExecutionResult:
    tool_name: str
    http_status: int
    error_code: Optional[str]
    replayed: bool
    body: Any
    sent_arguments: dict[str, Any]
    model_arguments: dict[str, Any]

class HttpToolsClient:
    def __init__(self, base_url: str, agent_token: str):
        self.base_url = base_url.rstrip("/")
        self.agent_token = agent_token
        self.client = httpx.Client(base_url=self.base_url, timeout=10.0)

    def close(self):
        self.client.close()

    def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str,
        run_id: str,
    ) -> ToolExecutionResult:
        headers = {
            "Authorization": f"Bearer {self.agent_token}",
            "X-Run-Id": run_id,
        }

        model_arguments = dict(arguments)
        sent_arguments = dict(arguments)

        try:
            if tool_name == "get_contract":
                contract_id = arguments.get("contractId", "")
                resp = self.client.get(f"/api/v1/contracts/{contract_id}", headers=headers)

            elif tool_name == "create_tenant":
                headers["Idempotency-Key"] = idempotency_key
                # The loop strips unknown fields (e.g. seats, modules) before the HTTP call
                sent_arguments = {"contractId": arguments.get("contractId", "")}
                resp = self.client.post("/api/v1/tenants", json=sent_arguments, headers=headers)

            elif tool_name == "set_region":
                tenant_id = arguments.get("tenantId", "")
                sent_arguments = {"region": arguments.get("region")}
                resp = self.client.post(f"/api/v1/tenants/{tenant_id}/region", json=sent_arguments, headers=headers)

            elif tool_name == "enable_module":
                tenant_id = arguments.get("tenantId", "")
                sent_arguments = {"module": arguments.get("module")}
                resp = self.client.post(f"/api/v1/tenants/{tenant_id}/modules", json=sent_arguments, headers=headers)

            elif tool_name == "invite_admin":
                tenant_id = arguments.get("tenantId", "")
                sent_arguments = {"email": arguments.get("email")}
                resp = self.client.post(f"/api/v1/tenants/{tenant_id}/invites", json=sent_arguments, headers=headers)

            elif tool_name == "create_task":
                tenant_id = arguments.get("tenantId", "")
                sent_arguments = {"code": arguments.get("code")}
                resp = self.client.post(f"/api/v1/tenants/{tenant_id}/tasks", json=sent_arguments, headers=headers)

            elif tool_name == "get_tenant":
                tenant_id = arguments.get("tenantId", "")
                resp = self.client.get(f"/api/v1/tenants/{tenant_id}", headers=headers)

            else:
                # Unknown tool name: record a step with HTTP 400 and code VALIDATION_ERROR
                return ToolExecutionResult(
                    tool_name=tool_name,
                    http_status=400,
                    error_code="VALIDATION_ERROR",
                    replayed=False,
                    body={"code": "VALIDATION_ERROR", "detail": f"Unknown tool: {tool_name}"},
                    sent_arguments=sent_arguments,
                    model_arguments=model_arguments,
                )

            http_status = resp.status_code
            replayed = resp.headers.get("Idempotent-Replayed", "").lower() == "true"
            try:
                body = resp.json()
            except Exception:
                body = resp.text

            error_code = None
            if isinstance(body, dict) and "code" in body:
                error_code = body["code"]

            return ToolExecutionResult(
                tool_name=tool_name,
                http_status=http_status,
                error_code=error_code,
                replayed=replayed,
                body=body,
                sent_arguments=sent_arguments,
                model_arguments=model_arguments,
            )

        except Exception as e:
            return ToolExecutionResult(
                tool_name=tool_name,
                http_status=500,
                error_code="CLIENT_ERROR",
                replayed=False,
                body={"code": "CLIENT_ERROR", "detail": str(e)},
                sent_arguments=sent_arguments,
                model_arguments=model_arguments,
            )

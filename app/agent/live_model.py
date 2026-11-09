import json
from typing import Any, Optional
import httpx

SYSTEM_PROMPT = """You provision a Fieldbase tenant by calling tools. The stored contract is the only source of truth for region, modules, seats, admins, and SSO.

Call get_contract first. Then create_tenant, set_region to the contract region, enable_module for each purchased module only, and invite_admin for each contract admin email only.

If ssoRequired is true and ssoMetadataPresent is false, call create_task with code collect_sso_metadata. Otherwise do not create a task.

If a tool returns an error, leave that request failed and continue with what the contract allows. Do not retry a MODULE_NOT_PURCHASED call with a different story.

Call get_tenant before you finish. Finish when region, modules, and admins match the contract, and the SSO task exists when SSO metadata is still required.

Do not say the account is live. You cannot mark it live, send email, or record SSO metadata."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_contract",
            "description": "Fetch contract by contract ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "contractId": {"type": "string", "description": "The contract ID"}
                },
                "required": ["contractId"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_tenant",
            "description": "Create tenant for the contract",
            "parameters": {
                "type": "object",
                "properties": {
                    "contractId": {"type": "string", "description": "The contract ID"}
                },
                "required": ["contractId"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_region",
            "description": "Set tenant region",
            "parameters": {
                "type": "object",
                "properties": {
                    "tenantId": {"type": "string"},
                    "region": {"type": "string"},
                },
                "required": ["tenantId", "region"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enable_module",
            "description": "Enable a module on a tenant",
            "parameters": {
                "type": "object",
                "properties": {
                    "tenantId": {"type": "string"},
                    "module": {"type": "string"},
                },
                "required": ["tenantId", "module"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "invite_admin",
            "description": "Invite an admin to the tenant",
            "parameters": {
                "type": "object",
                "properties": {
                    "tenantId": {"type": "string"},
                    "email": {"type": "string"},
                },
                "required": ["tenantId", "email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a task for the tenant",
            "parameters": {
                "type": "object",
                "properties": {
                    "tenantId": {"type": "string"},
                    "code": {"type": "string"},
                },
                "required": ["tenantId", "code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tenant",
            "description": "Get tenant state and checklist",
            "parameters": {
                "type": "object",
                "properties": {
                    "tenantId": {"type": "string"}
                },
                "required": ["tenantId"],
            },
        },
    },
]

class LiveModel:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        scenario: str,
        contract_id: str,
        idempotency_key: str,
        scenario_message: str,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.scenario = scenario
        self.contract_id = contract_id
        self.idempotency_key = idempotency_key

        user_content = f"{scenario_message}\ncontractId: {contract_id}\nidempotencyKey: {idempotency_key}"
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        self.current_call_id: Optional[str] = None
        self.total_tokens: Optional[int] = None
        self.client = httpx.Client(transport=transport, timeout=30.0)

    def close(self):
        self.client.close()

    def receive_result(self, tool_name: str, result_body: Any) -> None:
        call_id = self.current_call_id or "call_tool"
        content_str = json.dumps(result_body) if not isinstance(result_body, str) else result_body
        self.messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "name": tool_name,
            "content": content_str,
        })
        self.current_call_id = None

    def next_action(self) -> dict[str, Any]:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            url = base
        elif base.endswith("/v1"):
            url = f"{base}/chat/completions"
        else:
            url = f"{base}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": self.messages,
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        try:
            resp = self.client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            # Model error
            return {"stop": True, "final_text": f"MODEL_ERROR: {str(e)}"}

        # Extract token usage if provided
        usage = data.get("usage")
        if isinstance(usage, dict) and "total_tokens" in usage:
            if self.total_tokens is None:
                self.total_tokens = 0
            self.total_tokens += usage["total_tokens"]

        choices = data.get("choices", [])
        if not choices:
            return {"stop": True, "final_text": ""}

        msg = choices[0].get("message", {})
        tool_calls = msg.get("tool_calls", [])

        if tool_calls:
            first_call = tool_calls[0]
            self.current_call_id = first_call.get("id", "call_tool")
            fn = first_call.get("function", {})
            tool_name = fn.get("name", "")

            raw_args = fn.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    arguments = json.loads(raw_args)
                except Exception:
                    arguments = {}
            elif isinstance(raw_args, dict):
                arguments = raw_args
            else:
                arguments = {}

            # Append the assistant message with tool_calls to conversation history
            self.messages.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": tool_calls,
            })

            return {"tool": tool_name, "arguments": arguments}

        # No tool calls -> model finished
        final_text = msg.get("content", "") or ""
        self.messages.append({"role": "assistant", "content": final_text})
        return {"stop": True, "final_text": final_text}

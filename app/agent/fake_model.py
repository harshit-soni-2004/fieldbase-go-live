from typing import Any, Optional

class FakeModel:
    def __init__(self, scenario: str, contract_id: str):
        self.scenario = scenario
        self.contract_id = contract_id
        self.step_index = 0
        self.tenant_id: Optional[str] = None

    def receive_result(self, tool_name: str, result_body: Any) -> None:
        if tool_name == "create_tenant" and isinstance(result_body, dict):
            if "tenantId" in result_body:
                self.tenant_id = result_body["tenantId"]

    def next_action(self) -> dict[str, Any]:
        self.step_index += 1
        scenario_key = "northwind" if self.scenario in ("northwind", "northwind_retry") else self.scenario

        if scenario_key == "northwind":
            if self.step_index == 1:
                return {"tool": "get_contract", "arguments": {"contractId": self.contract_id}}
            elif self.step_index == 2:
                return {"tool": "create_tenant", "arguments": {"contractId": self.contract_id}}
            elif self.step_index == 3:
                return {"tool": "set_region", "arguments": {"tenantId": self.tenant_id, "region": "ap-south-1"}}
            elif self.step_index == 4:
                return {"tool": "enable_module", "arguments": {"tenantId": self.tenant_id, "module": "projects"}}
            elif self.step_index == 5:
                return {"tool": "enable_module", "arguments": {"tenantId": self.tenant_id, "module": "time"}}
            elif self.step_index == 6:
                return {"tool": "invite_admin", "arguments": {"tenantId": self.tenant_id, "email": "asha@northwind.example"}}
            elif self.step_index == 7:
                return {"tool": "invite_admin", "arguments": {"tenantId": self.tenant_id, "email": "dev@northwind.example"}}
            elif self.step_index == 8:
                return {"tool": "create_task", "arguments": {"tenantId": self.tenant_id, "code": "collect_sso_metadata"}}
            elif self.step_index == 9:
                return {"tool": "get_tenant", "arguments": {"tenantId": self.tenant_id}}
            else:
                return {"stop": True, "final_text": ""}

        elif scenario_key == "contoso":
            if self.step_index == 1:
                return {"tool": "get_contract", "arguments": {"contractId": self.contract_id}}
            elif self.step_index == 2:
                return {"tool": "create_tenant", "arguments": {"contractId": self.contract_id}}
            elif self.step_index == 3:
                return {"tool": "set_region", "arguments": {"tenantId": self.tenant_id, "region": "us-east-1"}}
            elif self.step_index == 4:
                return {"tool": "enable_module", "arguments": {"tenantId": self.tenant_id, "module": "projects"}}
            elif self.step_index == 5:
                return {"tool": "enable_module", "arguments": {"tenantId": self.tenant_id, "module": "billing"}}
            elif self.step_index == 6:
                return {"tool": "invite_admin", "arguments": {"tenantId": self.tenant_id, "email": "mia@contoso.example"}}
            elif self.step_index == 7:
                return {"tool": "get_tenant", "arguments": {"tenantId": self.tenant_id}}
            else:
                return {"stop": True, "final_text": ""}

        elif scenario_key == "fabrik":
            if self.step_index == 1:
                return {"tool": "get_contract", "arguments": {"contractId": self.contract_id}}
            elif self.step_index == 2:
                return {"tool": "create_tenant", "arguments": {"contractId": self.contract_id}}
            elif self.step_index == 3:
                return {"tool": "set_region", "arguments": {"tenantId": self.tenant_id, "region": "eu-west-1"}}
            elif self.step_index == 4:
                return {"tool": "enable_module", "arguments": {"tenantId": self.tenant_id, "module": "projects"}}
            elif self.step_index == 5:
                return {"tool": "enable_module", "arguments": {"tenantId": self.tenant_id, "module": "time"}}
            elif self.step_index == 6:
                return {"tool": "invite_admin", "arguments": {"tenantId": self.tenant_id, "email": "lena@fabrik.example"}}
            elif self.step_index == 7:
                return {"tool": "get_tenant", "arguments": {"tenantId": self.tenant_id}}
            else:
                return {"stop": True, "final_text": ""}

        return {"stop": True, "final_text": ""}


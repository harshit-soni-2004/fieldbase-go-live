import json
from fastapi.testclient import TestClient
import httpx
import pytest
from app.agent.live_model import SYSTEM_PROMPT, LiveModel
from app.db import get_connection

def test_live_mode_missing_env(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    resp = client.post("/api/demo/run", json={"scenario": "northwind", "mode": "live"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "LIVE_MODEL_NOT_CONFIGURED"

    # Verify no tenant row was written
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM tenants")
        assert cursor.fetchone()["cnt"] == 0

def test_live_model_parses_tool_call():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers.get("Authorization") == "Bearer fake-test-key"

        req_json = json.loads(request.content.decode("utf-8"))
        assert req_json["model"] == "test-model-4"
        assert req_json["temperature"] == 0
        assert req_json["messages"][0]["content"] == SYSTEM_PROMPT
        assert "contractId: ctr_northwind" in req_json["messages"][1]["content"]

        # Return mock tool call for get_contract
        mock_body = {
            "id": "chatcmpl-test",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_12345",
                                "type": "function",
                                "function": {
                                    "name": "get_contract",
                                    "arguments": json.dumps({"contractId": "ctr_northwind"}),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 15,
                "total_tokens": 65,
            },
        }
        return httpx.Response(200, json=mock_body)

    transport = httpx.MockTransport(mock_handler)

    model = LiveModel(
        base_url="http://fake-host",
        api_key="fake-test-key",
        model="test-model-4",
        scenario="northwind",
        contract_id="ctr_northwind",
        idempotency_key="prov-nw-001",
        scenario_message="Provision Northwind from this contract.",
        transport=transport,
    )

    action = model.next_action()
    assert action["tool"] == "get_contract"
    assert action["arguments"] == {"contractId": "ctr_northwind"}
    assert model.total_tokens == 65

    # Pass tool result
    model.receive_result("get_contract", {"contractId": "ctr_northwind", "customerName": "Northwind"})
    assert len(model.messages) == 4
    assert model.messages[-1]["role"] == "tool"
    assert model.messages[-1]["name"] == "get_contract"
    assert "ctr_northwind" in model.messages[-1]["content"]

    model.close()

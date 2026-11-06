import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.domain.policies import check_seat_cap
from app.api.problems import ProblemException

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

def load_fixture(filename: str) -> dict:
    with open(FIXTURES_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)

def create_contract_helper(client: TestClient, fixture_name: str, agent_headers: dict) -> dict:
    data = load_fixture(fixture_name)
    resp = client.post("/api/v1/contracts", json=data, headers=agent_headers)
    assert resp.status_code in (200, 201)
    return data

def test_create_requires_idempotency_key(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    resp = client.post(
        "/api/v1/tenants",
        json={"contractId": "ctr_northwind"},
        headers=agent_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "IDEMPOTENCY_KEY_MISSING"

def test_create_copies_seats_and_leaves_region_null(client: TestClient, agent_headers: dict):
    contract = create_contract_helper(client, "northwind.json", agent_headers)
    headers = {**agent_headers, "Idempotency-Key": "test-key-1"}

    # Extra body seats should be rejected with 422 VALIDATION_ERROR
    bad_resp = client.post(
        "/api/v1/tenants",
        json={"contractId": "ctr_northwind", "seats": 999},
        headers=headers,
    )
    assert bad_resp.status_code == 422
    assert bad_resp.json()["code"] == "VALIDATION_ERROR"

    # Legal body stores contract seats and null region
    resp = client.post(
        "/api/v1/tenants",
        json={"contractId": "ctr_northwind"},
        headers=headers,
    )
    assert resp.status_code == 201
    tenant = resp.json()
    assert tenant["seats"] == contract["seats"]
    assert tenant["region"] is None
    assert tenant["status"] == "provisioning"
    assert tenant["live"] is False

def test_region_must_match_contract(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    headers = {**agent_headers, "Idempotency-Key": "test-key-region"}
    resp = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=headers)
    tenant_id = resp.json()["tenantId"]

    # Wrong region returns REGION_MISMATCH (northwind is ap-south-1)
    bad_resp = client.post(
        f"/api/v1/tenants/{tenant_id}/region",
        json={"region": "us-east-1"},
        headers=agent_headers,
    )
    assert bad_resp.status_code == 422
    assert bad_resp.json()["code"] == "REGION_MISMATCH"

    # Contract region succeeds
    ok_resp = client.post(
        f"/api/v1/tenants/{tenant_id}/region",
        json={"region": "ap-south-1"},
        headers=agent_headers,
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["region"] == "ap-south-1"

def test_region_replay_and_conflict(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    headers = {**agent_headers, "Idempotency-Key": "test-key-region-conflict"}
    resp = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=headers)
    tenant_id = resp.json()["tenantId"]

    # Set region
    r1 = client.post(
        f"/api/v1/tenants/{tenant_id}/region",
        json={"region": "ap-south-1"},
        headers=agent_headers,
    )
    assert r1.status_code == 200

    # Same region replays with 200 and header
    r2 = client.post(
        f"/api/v1/tenants/{tenant_id}/region",
        json={"region": "ap-south-1"},
        headers=agent_headers,
    )
    assert r2.status_code == 200
    assert r2.headers.get("Idempotent-Replayed") == "true"

    # Second different region is REGION_ALREADY_SET
    r3 = client.post(
        f"/api/v1/tenants/{tenant_id}/region",
        json={"region": "eu-west-1"},
        headers=agent_headers,
    )
    assert r3.status_code == 409
    assert r3.json()["code"] == "REGION_ALREADY_SET"

def test_module_not_purchased(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "contoso.json", agent_headers)
    headers = {**agent_headers, "Idempotency-Key": "test-key-contoso"}
    t_resp = client.post("/api/v1/tenants", json={"contractId": "ctr_contoso"}, headers=headers)
    tenant_id = t_resp.json()["tenantId"]

    # Contoso only purchased projects, billing should return MODULE_NOT_PURCHASED
    m_resp = client.post(
        f"/api/v1/tenants/{tenant_id}/modules",
        json={"module": "billing"},
        headers=agent_headers,
    )
    assert m_resp.status_code == 422
    assert m_resp.json()["code"] == "MODULE_NOT_PURCHASED"

    # Check that tenant module list does not include billing
    get_resp = client.get(f"/api/v1/tenants/{tenant_id}", headers=agent_headers)
    assert "billing" not in get_resp.json()["modules"]

def test_unknown_module_on_tenant(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "contoso.json", agent_headers)
    headers = {**agent_headers, "Idempotency-Key": "test-key-mod-unknown"}
    t_resp = client.post("/api/v1/tenants", json={"contractId": "ctr_contoso"}, headers=headers)
    tenant_id = t_resp.json()["tenantId"]

    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/modules",
        json={"module": "analytics"},
        headers=agent_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "UNKNOWN_MODULE"

def test_enable_replay(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "contoso.json", agent_headers)
    headers = {**agent_headers, "Idempotency-Key": "test-key-mod-replay"}
    t_resp = client.post("/api/v1/tenants", json={"contractId": "ctr_contoso"}, headers=headers)
    tenant_id = t_resp.json()["tenantId"]

    # First enable
    r1 = client.post(
        f"/api/v1/tenants/{tenant_id}/modules",
        json={"module": "projects"},
        headers=agent_headers,
    )
    assert r1.status_code == 200
    assert r1.json() == ["projects"]

    # Second enable replays with header
    r2 = client.post(
        f"/api/v1/tenants/{tenant_id}/modules",
        json={"module": "projects"},
        headers=agent_headers,
    )
    assert r2.status_code == 200
    assert r2.headers.get("Idempotent-Replayed") == "true"
    assert r2.json() == ["projects"]

def test_invite_unknown_email(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    headers = {**agent_headers, "Idempotency-Key": "test-key-invite-unknown"}
    t_resp = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=headers)
    tenant_id = t_resp.json()["tenantId"]

    resp = client.post(
        f"/api/v1/tenants/{tenant_id}/invites",
        json={"email": "stranger@other.example"},
        headers=agent_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "EMAIL_NOT_ON_CONTRACT"

def test_invite_replay(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    headers = {**agent_headers, "Idempotency-Key": "test-key-invite-replay"}
    t_resp = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=headers)
    tenant_id = t_resp.json()["tenantId"]

    # First invite
    r1 = client.post(
        f"/api/v1/tenants/{tenant_id}/invites",
        json={"email": "asha@northwind.example"},
        headers=agent_headers,
    )
    assert r1.status_code == 200
    assert r1.json() == {"email": "asha@northwind.example", "name": "Asha Rao"}

    # Second invite replays
    r2 = client.post(
        f"/api/v1/tenants/{tenant_id}/invites",
        json={"email": "asha@northwind.example"},
        headers=agent_headers,
    )
    assert r2.status_code == 200
    assert r2.headers.get("Idempotent-Replayed") == "true"
    assert r2.json() == {"email": "asha@northwind.example", "name": "Asha Rao"}

def test_seat_cap_backstop(client: TestClient, agent_headers: dict):
    # Unit test on the policy seat function
    with pytest.raises(ProblemException) as excinfo:
        check_seat_cap(seats=1, current_invite_count=1, is_already_invited=False)
    assert excinfo.value.code == "SEAT_CAP"

    # Replay on already invited does not raise
    check_seat_cap(seats=1, current_invite_count=1, is_already_invited=True)

def test_task_only_when_sso_required(client: TestClient, agent_headers: dict):
    # Contoso does not require SSO
    create_contract_helper(client, "contoso.json", agent_headers)
    headers_c = {**agent_headers, "Idempotency-Key": "test-key-task-c"}
    t_c = client.post("/api/v1/tenants", json={"contractId": "ctr_contoso"}, headers=headers_c).json()
    resp_c = client.post(
        f"/api/v1/tenants/{t_c['tenantId']}/tasks",
        json={"code": "collect_sso_metadata"},
        headers=agent_headers,
    )
    assert resp_c.status_code == 422
    assert resp_c.json()["code"] == "TASK_NOT_APPLICABLE"

    # Northwind requires SSO
    create_contract_helper(client, "northwind.json", agent_headers)
    headers_n = {**agent_headers, "Idempotency-Key": "test-key-task-n"}
    t_n = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=headers_n).json()

    resp_n1 = client.post(
        f"/api/v1/tenants/{t_n['tenantId']}/tasks",
        json={"code": "collect_sso_metadata"},
        headers=agent_headers,
    )
    assert resp_n1.status_code == 200
    assert resp_n1.json()["status"] == "open"
    assert resp_n1.json()["code"] == "collect_sso_metadata"

    # Second call replays
    resp_n2 = client.post(
        f"/api/v1/tenants/{t_n['tenantId']}/tasks",
        json={"code": "collect_sso_metadata"},
        headers=agent_headers,
    )
    assert resp_n2.status_code == 200
    assert resp_n2.headers.get("Idempotent-Replayed") == "true"

def test_create_idempotent_replay(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    headers = {**agent_headers, "Idempotency-Key": "prov-nw-001"}

    resp1 = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=headers)
    assert resp1.status_code == 201
    tid1 = resp1.json()["tenantId"]

    resp2 = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=headers)
    assert resp2.status_code == 200
    assert resp2.headers.get("Idempotent-Replayed") == "true"
    assert resp2.json()["tenantId"] == tid1

def test_key_reused_for_other_contract(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    create_contract_helper(client, "contoso.json", agent_headers)
    headers = {**agent_headers, "Idempotency-Key": "shared-key-1"}

    resp1 = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=headers)
    assert resp1.status_code == 201

    resp2 = client.post("/api/v1/tenants", json={"contractId": "ctr_contoso"}, headers=headers)
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

def test_second_key_same_contract(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    h1 = {**agent_headers, "Idempotency-Key": "first-key"}
    h2 = {**agent_headers, "Idempotency-Key": "second-key"}

    resp1 = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=h1)
    assert resp1.status_code == 201

    resp2 = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=h2)
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "CONTRACT_ALREADY_PROVISIONED"

def test_agent_cannot_go_live(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "fabrik.json", agent_headers)
    h = {**agent_headers, "Idempotency-Key": "key-agent-live"}
    t = client.post("/api/v1/tenants", json={"contractId": "ctr_fabrik"}, headers=h).json()

    resp = client.post(f"/api/v1/tenants/{t['tenantId']}/go-live", json={}, headers=agent_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "AGENT_FORBIDDEN"

    get_resp = client.get(f"/api/v1/tenants/{t['tenantId']}", headers=agent_headers)
    assert get_resp.json()["live"] is False

def test_agent_cannot_record_sso(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    h = {**agent_headers, "Idempotency-Key": "key-agent-sso"}
    t = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=h).json()

    resp = client.post(f"/api/v1/tenants/{t['tenantId']}/sso-metadata", json={}, headers=agent_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "AGENT_FORBIDDEN"

def test_go_live_blocked_for_northwind(client: TestClient, agent_headers: dict, operator_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    h = {**agent_headers, "Idempotency-Key": "key-nw-sso-block"}
    t = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=h).json()
    tid = t["tenantId"]

    # Configure region, modules, invites, task
    client.post(f"/api/v1/tenants/{tid}/region", json={"region": "ap-south-1"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/modules", json={"module": "projects"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/modules", json={"module": "time"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/invites", json={"email": "asha@northwind.example"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/invites", json={"email": "dev@northwind.example"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/tasks", json={"code": "collect_sso_metadata"}, headers=agent_headers)

    get_t = client.get(f"/api/v1/tenants/{tid}", headers=agent_headers).json()
    assert get_t["status"] == "waiting_on_customer"

    # Operator go-live returns SSO_NOT_READY
    live_resp = client.post(f"/api/v1/tenants/{tid}/go-live", json={}, headers=operator_headers)
    assert live_resp.status_code == 409
    assert live_resp.json()["code"] == "SSO_NOT_READY"

def test_sso_then_go_live(client: TestClient, agent_headers: dict, operator_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    h = {**agent_headers, "Idempotency-Key": "key-nw-sso-success"}
    t = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=h).json()
    tid = t["tenantId"]

    # Provision fully
    client.post(f"/api/v1/tenants/{tid}/region", json={"region": "ap-south-1"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/modules", json={"module": "projects"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/modules", json={"module": "time"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/invites", json={"email": "asha@northwind.example"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/invites", json={"email": "dev@northwind.example"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/tasks", json={"code": "collect_sso_metadata"}, headers=agent_headers)

    # Record SSO metadata
    sso_resp = client.post(f"/api/v1/tenants/{tid}/sso-metadata", json={}, headers=operator_headers)
    assert sso_resp.status_code == 200
    t_after_sso = sso_resp.json()
    assert t_after_sso["status"] == "ready_for_review"
    assert t_after_sso["tasks"][0]["status"] == "done"

    # Now go-live succeeds
    live_resp = client.post(f"/api/v1/tenants/{tid}/go-live", json={}, headers=operator_headers)
    assert live_resp.status_code == 200
    t_live = live_resp.json()
    assert t_live["live"] is True
    assert t_live["status"] == "live"

def test_go_live_incomplete_checklist(client: TestClient, agent_headers: dict, operator_headers: dict):
    create_contract_helper(client, "fabrik.json", agent_headers)
    h = {**agent_headers, "Idempotency-Key": "key-fabrik-incomplete"}
    t = client.post("/api/v1/tenants", json={"contractId": "ctr_fabrik"}, headers=h).json()
    tid = t["tenantId"]

    # Region set, but modules not yet enabled
    client.post(f"/api/v1/tenants/{tid}/region", json={"region": "eu-west-1"}, headers=agent_headers)

    live_resp = client.post(f"/api/v1/tenants/{tid}/go-live", json={}, headers=operator_headers)
    assert live_resp.status_code == 409
    assert live_resp.json()["code"] == "CHECKLIST_INCOMPLETE"

def test_already_live_rejects_module_write(client: TestClient, agent_headers: dict, operator_headers: dict):
    create_contract_helper(client, "fabrik.json", agent_headers)
    h = {**agent_headers, "Idempotency-Key": "key-fabrik-already-live"}
    t = client.post("/api/v1/tenants", json={"contractId": "ctr_fabrik"}, headers=h).json()
    tid = t["tenantId"]

    # Complete checklist
    client.post(f"/api/v1/tenants/{tid}/region", json={"region": "eu-west-1"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/modules", json={"module": "projects"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/modules", json={"module": "time"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/invites", json={"email": "lena@fabrik.example"}, headers=agent_headers)

    # Mark live
    live_resp = client.post(f"/api/v1/tenants/{tid}/go-live", json={}, headers=operator_headers)
    assert live_resp.status_code == 200

    # Module write now rejected with ALREADY_LIVE
    m_resp = client.post(f"/api/v1/tenants/{tid}/modules", json={"module": "projects"}, headers=agent_headers)
    assert m_resp.status_code == 409
    assert m_resp.json()["code"] == "ALREADY_LIVE"

    # Second go-live returns ALREADY_LIVE
    live_resp2 = client.post(f"/api/v1/tenants/{tid}/go-live", json={}, headers=operator_headers)
    assert live_resp2.status_code == 409
    assert live_resp2.json()["code"] == "ALREADY_LIVE"

def test_checklist_exact_modules(client: TestClient, agent_headers: dict):
    create_contract_helper(client, "northwind.json", agent_headers)
    h = {**agent_headers, "Idempotency-Key": "key-exact-modules"}
    t = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=h).json()
    tid = t["tenantId"]

    client.post(f"/api/v1/tenants/{tid}/region", json={"region": "ap-south-1"}, headers=agent_headers)
    client.post(f"/api/v1/tenants/{tid}/modules", json={"module": "projects"}, headers=agent_headers)
    # Only projects enabled so far
    t_partial = client.get(f"/api/v1/tenants/{tid}", headers=agent_headers).json()
    assert t_partial["checklist"]["modules"]["ok"] is False

    # Enable time
    client.post(f"/api/v1/tenants/{tid}/modules", json={"module": "time"}, headers=agent_headers)
    t_full = client.get(f"/api/v1/tenants/{tid}", headers=agent_headers).json()
    assert t_full["checklist"]["modules"]["ok"] is True
    assert t_full["checklist"]["modules"]["actual"] == ["projects", "time"]
    assert t_full["checklist"]["modules"]["expected"] == ["projects", "time"]

def test_audit_event_logged(client: TestClient, agent_headers: dict):
    from app.db import get_connection
    create_contract_helper(client, "northwind.json", agent_headers)
    headers = {**agent_headers, "Idempotency-Key": "audit-test-key", "X-Run-Id": "run_test123"}
    resp = client.post("/api/v1/tenants", json={"contractId": "ctr_northwind"}, headers=headers)
    assert resp.status_code == 201

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_events WHERE run_id = ?", ("run_test123",))
        event = cursor.fetchone()
        assert event is not None
        assert event["actor"] == "agent"
        assert event["method"] == "POST"
        assert event["path"] == "/api/v1/tenants"
        assert event["http_status"] == 201
        assert "ctr_northwind" in event["request_json"]
        assert "tenantId" in event["response_json"]


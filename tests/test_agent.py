import ast
from pathlib import Path
import pytest
import httpx
from app.db import get_connection

def test_northwind_script(live_client: httpx.Client):
    resp = live_client.post("/api/demo/run", json={"scenario": "northwind", "mode": "fake"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["stoppedReason"] == "model_stop"
    assert len(data["steps"]) == 9
    tenant = data["tenant"]
    assert tenant["status"] == "waiting_on_customer"
    assert tenant["live"] is False
    assert tenant["modules"] == ["projects", "time"]

    invite_emails = [i["email"] for i in tenant["invites"]]
    assert sorted(invite_emails) == ["asha@northwind.example", "dev@northwind.example"]

    assert len(tenant["tasks"]) == 1
    assert tenant["tasks"][0]["code"] == "collect_sso_metadata"
    assert tenant["tasks"][0]["status"] == "open"

def test_contoso_billing_rejected(live_client: httpx.Client):
    resp = live_client.post("/api/demo/run", json={"scenario": "contoso", "mode": "fake"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Step 5 must be enable_module billing returning 422 MODULE_NOT_PURCHASED
    billing_steps = [s for s in data["steps"] if s["toolName"] == "enable_module" and s["arguments"].get("module") == "billing"]
    assert len(billing_steps) == 1
    billing_step = billing_steps[0]
    assert billing_step["httpStatus"] == 422
    assert billing_step["errorCode"] == "MODULE_NOT_PURCHASED"

    tenant = data["tenant"]
    assert tenant["status"] == "ready_for_review"
    assert tenant["modules"] == ["projects"]
    assert len(tenant["invites"]) == 1
    assert tenant["invites"][0]["email"] == "mia@contoso.example"
    assert len(tenant["tasks"]) == 0

def test_fabrik_ready(live_client: httpx.Client):
    resp = live_client.post("/api/demo/run", json={"scenario": "fabrik", "mode": "fake"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    tenant = data["tenant"]
    assert tenant["status"] == "ready_for_review"
    tenant_id = tenant["tenantId"]

    # Demo go-live route proxies operator go-live
    live_resp = live_client.post(f"/api/demo/tenants/{tenant_id}/go-live", json={})
    assert live_resp.status_code == 200, live_resp.text
    live_data = live_resp.json()
    assert live_data["live"] is True
    assert live_data["status"] == "live"

def test_northwind_retry(live_client: httpx.Client):
    # First run: northwind
    r1 = live_client.post("/api/demo/run", json={"scenario": "northwind", "mode": "fake"})
    assert r1.status_code == 200
    t1 = r1.json()["tenant"]
    tenant_id1 = t1["tenantId"]

    # Second run: northwind_retry
    r2 = live_client.post("/api/demo/run", json={"scenario": "northwind_retry", "mode": "fake"})
    assert r2.status_code == 200
    data2 = r2.json()
    t2 = data2["tenant"]

    # Same tenant id
    assert t2["tenantId"] == tenant_id1

    # In database: one tenant row, two invites, one task
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM tenants WHERE contract_id = 'ctr_northwind'")
        assert cursor.fetchone()["cnt"] == 1

        cursor.execute("SELECT COUNT(*) as cnt FROM invites WHERE tenant_id = ?", (tenant_id1,))
        assert cursor.fetchone()["cnt"] == 2

        cursor.execute("SELECT COUNT(*) as cnt FROM tasks WHERE tenant_id = ?", (tenant_id1,))
        assert cursor.fetchone()["cnt"] == 1

    # At least the create step on the retry has replayed true
    create_step = [s for s in data2["steps"] if s["toolName"] == "create_tenant"][0]
    assert create_step["replayed"] is True

def test_retry_without_first_run(live_client: httpx.Client):
    # Empty DB: northwind_retry must return 409 VALIDATION_ERROR
    resp = live_client.post("/api/demo/run", json={"scenario": "northwind_retry", "mode": "fake"})
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"

def test_agent_package_has_no_db_import():
    agent_dir = Path(__file__).parent.parent / "app" / "agent"
    assert agent_dir.exists()

    forbidden_modules = {"app.db", "app.domain"}

    for py_file in agent_dir.glob("**/*.py"):
        code = py_file.read_text(encoding="utf-8")
        tree = ast.parse(code, filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_modules:
                        assert not alias.name.startswith(forbidden), (
                            f"{py_file} imports forbidden module '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_modules:
                        assert not node.module.startswith(forbidden), (
                            f"{py_file} imports from forbidden module '{node.module}'"
                        )


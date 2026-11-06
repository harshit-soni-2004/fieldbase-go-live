from fastapi.testclient import TestClient
import httpx

def test_index_has_title(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Go-live" in resp.text
    assert "Mark live" in resp.text

def test_demo_run_json_matches_northwind(live_client: httpx.Client):
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

    checklist = tenant["checklist"]
    assert checklist["region"]["ok"] is True
    assert checklist["modules"]["ok"] is True
    assert checklist["admins"]["ok"] is True
    assert checklist["sso"]["state"] == "blocking"
    assert checklist["sso"]["ok"] is False
    assert checklist["live"]["ok"] is False


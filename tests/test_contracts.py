import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

def load_fixture(filename: str) -> dict:
    with open(FIXTURES_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)

def test_load_three_fixtures(client: TestClient, agent_headers: dict):
    fixtures = ["northwind.json", "contoso.json", "fabrik.json"]
    for fixture_file in fixtures:
        data = load_fixture(fixture_file)
        contract_id = data["contractId"]

        # POST fixture
        response = client.post("/api/v1/contracts", json=data, headers=agent_headers)
        assert response.status_code == 201, f"Failed for {fixture_file}: {response.text}"
        created = response.json()
        assert created["contractId"] == contract_id
        assert created["customerName"] == data["customerName"]
        assert created["seats"] == data["seats"]

        # GET fixture
        get_resp = client.get(f"/api/v1/contracts/{contract_id}", headers=agent_headers)
        assert get_resp.status_code == 200
        fetched = get_resp.json()

        # Check modules match
        assert set(fetched["modules"]) == set(data["modules"])
        # Check catalog order: projects, time, billing
        catalog_order = ["projects", "time", "billing"]
        expected_modules = [m for m in catalog_order if m in data["modules"]]
        assert fetched["modules"] == expected_modules

        # Check emails match
        expected_emails = sorted([a["email"].lower() for a in data["admins"]])
        actual_emails = [a["email"] for a in fetched["admins"]]
        assert actual_emails == expected_emails

def test_unknown_module_rejected(client: TestClient, agent_headers: dict):
    data = load_fixture("contoso.json")
    data["contractId"] = "ctr_badmodule"
    data["modules"] = ["billingg"]

    response = client.post("/api/v1/contracts", json=data, headers=agent_headers)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "UNKNOWN_MODULE"

    # GET must be 404
    get_resp = client.get("/api/v1/contracts/ctr_badmodule", headers=agent_headers)
    assert get_resp.status_code == 404
    assert get_resp.json()["code"] == "CONTRACT_NOT_FOUND"

    # Also test another invalid module name like "crm"
    data["modules"] = ["crm"]
    response2 = client.post("/api/v1/contracts", json=data, headers=agent_headers)
    assert response2.status_code == 422
    assert response2.json()["code"] == "UNKNOWN_MODULE"

def test_unknown_region_rejected(client: TestClient, agent_headers: dict):
    data = load_fixture("contoso.json")
    data["contractId"] = "ctr_badregion"
    data["region"] = "us-west-2"

    response = client.post("/api/v1/contracts", json=data, headers=agent_headers)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "UNKNOWN_REGION"

    get_resp = client.get("/api/v1/contracts/ctr_badregion", headers=agent_headers)
    assert get_resp.status_code == 404

def test_too_many_admins_rejected(client: TestClient, agent_headers: dict):
    data = load_fixture("northwind.json")
    data["contractId"] = "ctr_toomanyadmins"
    data["seats"] = 1  # 2 admins in northwind, but seats=1

    response = client.post("/api/v1/contracts", json=data, headers=agent_headers)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "CONTRACT_SEAT_CONFLICT"

def test_same_contract_replays(client: TestClient, agent_headers: dict):
    data = load_fixture("northwind.json")
    # First post -> 201
    resp1 = client.post("/api/v1/contracts", json=data, headers=agent_headers)
    assert resp1.status_code == 201
    assert "Idempotent-Replayed" not in resp1.headers

    # Second identical post -> 200 with Idempotent-Replayed: true
    resp2 = client.post("/api/v1/contracts", json=data, headers=agent_headers)
    assert resp2.status_code == 200
    assert resp2.headers.get("Idempotent-Replayed") == "true"
    assert resp2.json()["contractId"] == data["contractId"]

def test_same_contract_id_different_body(client: TestClient, agent_headers: dict):
    data = load_fixture("northwind.json")
    # First post
    resp1 = client.post("/api/v1/contracts", json=data, headers=agent_headers)
    assert resp1.status_code == 201

    # Second post with modified seats
    modified_data = dict(data)
    modified_data["seats"] = 50
    resp2 = client.post("/api/v1/contracts", json=modified_data, headers=agent_headers)
    assert resp2.status_code == 409
    body = resp2.json()
    assert body["code"] == "IDEMPOTENCY_KEY_REUSED"

def test_unknown_json_fields_rejected(client: TestClient, agent_headers: dict):
    data = load_fixture("contoso.json")
    data["contractId"] = "ctr_extrafield"
    data["customExtraField"] = "unexpected"

    response = client.post("/api/v1/contracts", json=data, headers=agent_headers)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"

def test_auth_required(client: TestClient):
    data = load_fixture("contoso.json")
    # No auth header -> 401
    resp = client.post("/api/v1/contracts", json=data)
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"

    # Bad auth header -> 401
    resp_bad = client.post(
        "/api/v1/contracts",
        json=data,
        headers={"Authorization": "Bearer bad-token"},
    )
    assert resp_bad.status_code == 401
    assert resp_bad.json()["code"] == "UNAUTHORIZED"

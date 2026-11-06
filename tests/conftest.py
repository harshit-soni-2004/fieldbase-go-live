import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

os.environ["APP_ENV"] = "local"
os.environ["AGENT_TOKEN"] = "agent-local"
os.environ["OPERATOR_TOKEN"] = "operator-local"

from app.db import init_db
from app.main import app

@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_file)
    init_db(db_file)
    yield db_file

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def agent_headers():
    return {"Authorization": "Bearer agent-local"}

@pytest.fixture
def operator_headers():
    return {"Authorization": "Bearer operator-local"}

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

import socket
import threading
import time
import httpx
import uvicorn

def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

@pytest.fixture
def live_server(fresh_db):
    port = get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            with httpx.Client() as c:
                resp = c.get(f"{base_url}/api/v1/contracts/ctr_health")
                break
        except Exception:
            time.sleep(0.05)

    yield base_url
    server.should_exit = True
    thread.join(timeout=2)

@pytest.fixture
def live_client(live_server):
    with httpx.Client(base_url=live_server) as c:
        yield c



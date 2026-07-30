from fastapi.testclient import TestClient

from agent_platform.api.app import create_app


def test_health_live_and_ready() -> None:
    client = TestClient(create_app())
    live = client.get("/health/live")
    ready = client.get("/health/ready")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

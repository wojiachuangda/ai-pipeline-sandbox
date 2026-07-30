"""HTTP integration tests for health-check endpoints (/live, /ready)."""

from __future__ import annotations

from starlette.testclient import TestClient

from sandbox_app.api.health import app


client = TestClient(app)


# ---------------------------------------------------------------------------
# /live
# ---------------------------------------------------------------------------


def test_live_returns_200() -> None:
    """GET /live responds with 200 and {"status": "ok"}."""
    resp = client.get("/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_live_content_type_is_json() -> None:
    """GET /live returns application/json Content-Type."""
    resp = client.get("/live")
    assert resp.headers["content-type"].startswith("application/json")


# ---------------------------------------------------------------------------
# /ready
# ---------------------------------------------------------------------------


def test_ready_returns_200() -> None:
    """GET /ready responds with 200 and {"status": "ready"}."""
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


def test_ready_content_type_is_json() -> None:
    """GET /ready returns application/json Content-Type."""
    resp = client.get("/ready")
    assert resp.headers["content-type"].startswith("application/json")

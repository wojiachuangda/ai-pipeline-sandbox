"""API tests for Agent Registry — covers AC-1 through AC-5."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sandbox_app import create_app


def _client() -> TestClient:
    """Return a fresh TestClient with a clean store for each test."""
    app = create_app()
    return TestClient(app)


def _register(client: TestClient, *, name: str = "demo-bot", **overrides):
    """Helper: POST a valid agent and return the response."""
    payload = {
        "name": name,
        "agent_type": "chatbot",
        "owner_id": "user-1",
        "tenant_id": "tenant-a",
    }
    payload.update(overrides)
    return client.post("/agents", json=payload)


# ── AC-1: register success ─────────────────────────────────────────


def test_register_agent_ok() -> None:
    client = _client()

    resp = _register(client)

    assert resp.status_code == 201
    data = resp.json()
    assert "agent_id" in data
    assert data["name"] == "demo-bot"
    assert data["agent_type"] == "chatbot"
    assert data["owner_id"] == "user-1"
    assert data["tenant_id"] == "tenant-a"
    assert data["status"] == "INACTIVE"
    assert "created_at" in data
    assert data["description"] is None
    assert data["tags"] == []


# ── AC-2: duplicate name within same tenant ────────────────────────


def test_register_duplicate_name_same_tenant() -> None:
    client = _client()

    # First registration succeeds
    r1 = _register(client)
    assert r1.status_code == 201

    # Second with same tenant_id + name must fail
    r2 = _register(client)
    assert r2.status_code == 400
    assert r2.json()["detail"] == "AGENT_NAME_DUPLICATE"


def test_register_same_name_different_tenant() -> None:
    """Same name in a different tenant is allowed."""
    client = _client()

    r1 = _register(client, name="my-agent", tenant_id="tenant-a")
    assert r1.status_code == 201

    r2 = _register(client, name="my-agent", tenant_id="tenant-b")
    assert r2.status_code == 201
    assert r2.json()["agent_id"] != r1.json()["agent_id"]


# ── AC-3: GET by agent_id ──────────────────────────────────────────


def test_get_agent_found() -> None:
    client = _client()

    create_resp = _register(client)
    agent_id = create_resp.json()["agent_id"]

    resp = client.get(f"/agents/{agent_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == agent_id
    assert data["name"] == "demo-bot"


def test_get_agent_not_found() -> None:
    client = _client()

    resp = client.get("/agents/nonexistent-id")
    assert resp.status_code == 404


# ── AC-4: PATCH metadata update (description / tags / owner_id) ────


def test_update_agent_metadata() -> None:
    client = _client()

    # Create first
    create_resp = _register(client)
    agent_id = create_resp.json()["agent_id"]

    # Patch three fields
    patch = {"description": "A helpful assistant", "tags": ["nlp", "chat"], "owner_id": "user-2"}
    resp = client.patch(f"/agents/{agent_id}", json=patch)
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "A helpful assistant"
    assert data["tags"] == ["nlp", "chat"]
    assert data["owner_id"] == "user-2"
    # Unpatched fields remain unchanged
    assert data["name"] == "demo-bot"
    assert data["status"] == "INACTIVE"


def test_update_agent_not_found() -> None:
    client = _client()

    resp = client.patch("/agents/nonexistent-id", json={"description": "x"})
    assert resp.status_code == 404


def test_update_agent_partial() -> None:
    """PATCH with only a single field should update just that field."""
    client = _client()

    create_resp = _register(client)
    agent_id = create_resp.json()["agent_id"]

    # Only update description
    resp = client.patch(f"/agents/{agent_id}", json={"description": "partial"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "partial"
    # tags should remain unchanged
    assert data["tags"] == []

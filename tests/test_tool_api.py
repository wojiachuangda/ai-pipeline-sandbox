"""API tests for tool registration, bindings, and skill management."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sandbox_app.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Return a fresh TestClient with clean in-memory stores."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def client_with_limit_3() -> TestClient:
    """Return a client whose BindingStore has MAX_BINDINGS = 3."""
    from sandbox_app.tool_routes import init_stores
    from sandbox_app.tool_store import BindingStore, SkillStore, ToolStore

    app = create_app()
    init_stores(
        tool_store=ToolStore(),
        binding_store=BindingStore(max_bindings=3),
        skill_store=SkillStore(),
    )
    return TestClient(app)


def _register_tool(client: TestClient, name: str = "test-tool", **kwargs) -> dict:
    """Helper: register a tool and return the response dict."""
    payload = {"name": name, "tool_type": "API", "input_schema": {"type": "object"}, **kwargs}
    resp = client.post("/tools", json=payload)
    assert resp.status_code == 201
    return resp.json()


# ══════════════════════════════════════════════════════════════════════════════
# AC-1: Tool registration
# ══════════════════════════════════════════════════════════════════════════════


class TestToolRegistration:
    def test_register_tool_ok(self, client: TestClient) -> None:
        """Register tools of all four supported types and verify tool_id is returned."""
        for tt in ("API", "CLI", "FUNCTION", "MCP"):
            payload = {
                "name": f"{tt.lower()}-tool",
                "tool_type": tt,
                "input_schema": {"type": "object", "properties": {"x": {"type": "string"}}},
            }
            resp = client.post("/tools", json=payload)
            assert resp.status_code == 201, f"failed for {tt}: {resp.text}"
            body = resp.json()
            assert "tool_id" in body
            assert body["tool_type"] == tt
            assert body["name"] == f"{tt.lower()}-tool"
            assert body["input_schema"] == payload["input_schema"]
            assert "created_at" in body

    def test_register_tool_missing_input_schema(self, client: TestClient) -> None:
        """POST without input_schema must return 422 (Pydantic validation)."""
        payload = {"name": "bad", "tool_type": "CLI"}
        resp = client.post("/tools", json=payload)
        assert resp.status_code == 422

    def test_get_tool_found(self, client: TestClient) -> None:
        """GET /tools/{id} returns the tool."""
        created = _register_tool(client)
        resp = client.get(f"/tools/{created['tool_id']}")
        assert resp.status_code == 200
        assert resp.json() == created

    def test_get_tool_not_found(self, client: TestClient) -> None:
        """GET unknown tool_id returns 404."""
        resp = client.get("/tools/nonexistent-id")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "TOOL_NOT_FOUND"

    def test_endpoint_stored(self, client: TestClient) -> None:
        """MCP endpoint is stored as a string stub (AC-5: no real dial)."""
        created = _register_tool(
            client,
            name="mcp-stub",
            tool_type="MCP",
            endpoint="https://mcp.example.com/tools",
        )
        assert created["endpoint"] == "https://mcp.example.com/tools"


# ══════════════════════════════════════════════════════════════════════════════
# AC-2: Agent-tool binding
# ══════════════════════════════════════════════════════════════════════════════


class TestBindings:
    def test_create_binding_allow(self, client: TestClient) -> None:
        """Bind with ALLOW permission returns 201."""
        tool = _register_tool(client)
        payload = {
            "agent_id": "agent-1",
            "tool_id": tool["tool_id"],
            "permission": "ALLOW",
        }
        resp = client.post("/bindings", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "binding_id" in body
        assert body["permission"] == "ALLOW"

    def test_create_binding_deny(self, client: TestClient) -> None:
        """Bind with DENY permission returns 201."""
        tool = _register_tool(client)
        payload = {
            "agent_id": "agent-2",
            "tool_id": tool["tool_id"],
            "permission": "DENY",
        }
        resp = client.post("/bindings", json=payload)
        assert resp.status_code == 201

    def test_create_binding_with_approval_and_rate_limit(self, client: TestClient) -> None:
        """ALLOW_WITH_APPROVAL + rate_limit struct is preserved in response."""
        tool = _register_tool(client)
        payload = {
            "agent_id": "agent-3",
            "tool_id": tool["tool_id"],
            "permission": "ALLOW_WITH_APPROVAL",
            "rate_limit": {"max_requests": 100, "window_seconds": 60},
        }
        resp = client.post("/bindings", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["permission"] == "ALLOW_WITH_APPROVAL"
        assert body["rate_limit"] == {"max_requests": 100, "window_seconds": 60}

    def test_binding_limit_exceeded(self, client_with_limit_3: TestClient) -> None:
        """Creating N+1 bindings for same agent returns 400 BINDING_LIMIT_EXCEEDED."""
        client = client_with_limit_3
        tool = _register_tool(client)

        # Create 3 bindings (the limit) — all should succeed
        for i in range(3):
            resp = client.post(
                "/bindings",
                json={
                    "agent_id": "agent-full",
                    "tool_id": tool["tool_id"],
                    "permission": "ALLOW",
                },
            )
            assert resp.status_code == 201, f"binding {i} failed"

        # 4th binding should be rejected
        resp = client.post(
            "/bindings",
            json={
                "agent_id": "agent-full",
                "tool_id": tool["tool_id"],
                "permission": "ALLOW",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "BINDING_LIMIT_EXCEEDED"

    def test_binding_nonexistent_tool(self, client: TestClient) -> None:
        """Binding to a nonexistent tool_id returns 404."""
        payload = {
            "agent_id": "agent-1",
            "tool_id": "no-such-tool",
            "permission": "ALLOW",
        }
        resp = client.post("/bindings", json=payload)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "TOOL_NOT_FOUND"

    def test_list_bindings_by_agent(self, client: TestClient) -> None:
        """GET /bindings?agent_id= filters correctly."""
        tool = _register_tool(client)
        client.post(
            "/bindings",
            json={"agent_id": "a1", "tool_id": tool["tool_id"], "permission": "ALLOW"},
        )
        client.post(
            "/bindings",
            json={"agent_id": "a2", "tool_id": tool["tool_id"], "permission": "DENY"},
        )

        resp = client.get("/bindings?agent_id=a1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["agent_id"] == "a1"

    def test_delete_binding(self, client: TestClient) -> None:
        """DELETE /bindings/{id} returns 204 on success, 404 on unknown."""
        tool = _register_tool(client)
        created = client.post(
            "/bindings",
            json={"agent_id": "agent-del", "tool_id": tool["tool_id"], "permission": "ALLOW"},
        ).json()

        # Delete
        resp = client.delete(f"/bindings/{created['binding_id']}")
        assert resp.status_code == 204

        # Second delete → 404
        resp2 = client.delete(f"/bindings/{created['binding_id']}")
        assert resp2.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# AC-3: Skill metadata upload & status workflow
# ══════════════════════════════════════════════════════════════════════════════


class TestSkills:
    def test_create_skill_pending_review(self, client: TestClient) -> None:
        """POST /skills returns 201 with status PENDING_REVIEW."""
        payload = {
            "name": "my-skill",
            "description": "Does something useful",
            "file_path": "/tmp/skill.zip",
        }
        resp = client.post("/skills", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "skill_id" in body
        assert body["status"] == "PENDING_REVIEW"
        assert body["name"] == "my-skill"
        assert body["file_path"] == "/tmp/skill.zip"
        assert "created_at" in body

    def test_approve_skill(self, client: TestClient) -> None:
        """PATCH /skills/{id}/status APPROVED succeeds from PENDING_REVIEW."""
        created = client.post("/skills", json={"name": "s1"}).json()
        resp = client.patch(
            f"/skills/{created['skill_id']}/status",
            json={"status": "APPROVED"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "APPROVED"

    def test_skill_invalid_status_transition(self, client: TestClient) -> None:
        """Cannot transition APPROVED → PENDING_REVIEW or APPROVED → APPROVED."""
        created = client.post("/skills", json={"name": "s2"}).json()

        # Approve once
        client.patch(
            f"/skills/{created['skill_id']}/status",
            json={"status": "APPROVED"},
        )

        # Try to approve again → 400
        resp = client.patch(
            f"/skills/{created['skill_id']}/status",
            json={"status": "APPROVED"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "INVALID_STATUS_TRANSITION"

        # Try to revert to PENDING_REVIEW → 400
        resp2 = client.patch(
            f"/skills/{created['skill_id']}/status",
            json={"status": "PENDING_REVIEW"},
        )
        assert resp2.status_code == 400
        assert resp2.json()["detail"] == "INVALID_STATUS_TRANSITION"

    def test_get_skill_not_found(self, client: TestClient) -> None:
        """GET unknown skill_id returns 404."""
        resp = client.get("/skills/nonexistent")
        assert resp.status_code == 404

    def test_update_status_skill_not_found(self, client: TestClient) -> None:
        """PATCH status for unknown skill returns 404."""
        resp = client.patch("/skills/nonexistent/status", json={"status": "APPROVED"})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "SKILL_NOT_FOUND"

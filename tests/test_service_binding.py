"""Tests for service binding: BIND, UNBIND, critical-service enforcement."""

from __future__ import annotations

import pytest

from sandbox_app.service_binding import (
    _reset_store,
    bind_service,
    get_bindings,
    has_critical_bindings,
    unbind_service,
)

AGENT_ID = "agent-bind-001"


@pytest.fixture(autouse=True)
def _clear_store() -> None:
    _reset_store()


# ---------------------------------------------------------------------------
# bind_service
# ---------------------------------------------------------------------------


def test_bind_service() -> None:
    b = bind_service(AGENT_ID, "LLM", "svc-llm-1")
    assert b.status == "BOUND"
    assert b.service_type == "LLM"
    assert b.service_instance_id == "svc-llm-1"


def test_bind_service_with_config() -> None:
    b = bind_service(AGENT_ID, "LLM", "svc-1", binding_config={"model": "gpt-4"})
    assert b.binding_config == {"model": "gpt-4"}


def test_bind_service_overwrites() -> None:
    bind_service(AGENT_ID, "LLM", "svc-1")
    b2 = bind_service(AGENT_ID, "LLM", "svc-1", binding_config={"model": "claude"})
    # same key, overwritten
    assert b2.binding_config == {"model": "claude"}


# ---------------------------------------------------------------------------
# unbind_service
# ---------------------------------------------------------------------------


def test_unbind_service() -> None:
    bind_service(AGENT_ID, "LLM", "svc-1")
    b = unbind_service(AGENT_ID, "LLM", "svc-1")
    assert b.status == "UNBOUND"


def test_unbind_nonexistent_creates_unbound() -> None:
    b = unbind_service(AGENT_ID, "LLM", "svc-new")
    assert b.status == "UNBOUND"
    assert b.service_type == "LLM"


def test_unbind_critical_service_while_active() -> None:
    bind_service(AGENT_ID, "LLM", "svc-1")
    with pytest.raises(ValueError, match="CRITICAL_SERVICE_IN_USE"):
        unbind_service(AGENT_ID, "LLM", "svc-1", agent_status="ACTIVE", agent_type="LLM")


def test_unbind_noncritical_while_active() -> None:
    # LLM agent type only requires LLM. EMBEDDING is non-critical for LLM agents.
    bind_service(AGENT_ID, "EMBEDDING", "emb-1")
    b = unbind_service(AGENT_ID, "EMBEDDING", "emb-1", agent_status="ACTIVE", agent_type="LLM")
    assert b.status == "UNBOUND"


def test_unbind_while_inactive_always_allowed() -> None:
    bind_service(AGENT_ID, "LLM", "svc-1")
    b = unbind_service(AGENT_ID, "LLM", "svc-1", agent_status="INACTIVE", agent_type="LLM")
    assert b.status == "UNBOUND"


# ---------------------------------------------------------------------------
# get_bindings
# ---------------------------------------------------------------------------


def test_get_bindings() -> None:
    bind_service(AGENT_ID, "LLM", "a")
    bind_service(AGENT_ID, "EMBEDDING", "b")
    bind_service("other-agent", "LLM", "c")

    mine = get_bindings(AGENT_ID)
    assert len(mine) == 2
    assert all(b.agent_id == AGENT_ID for b in mine)


# ---------------------------------------------------------------------------
# has_critical_bindings
# ---------------------------------------------------------------------------


def test_has_critical_bindings_llm() -> None:
    # LLM type requires LLM service
    assert has_critical_bindings(AGENT_ID, "LLM") is False
    bind_service(AGENT_ID, "LLM", "svc-1")
    assert has_critical_bindings(AGENT_ID, "LLM") is True


def test_has_critical_bindings_rag() -> None:
    # RAG requires LLM + EMBEDDING + VECTOR_DB
    assert has_critical_bindings(AGENT_ID, "RAG") is False
    bind_service(AGENT_ID, "LLM", "llm-1")
    assert has_critical_bindings(AGENT_ID, "RAG") is False
    bind_service(AGENT_ID, "EMBEDDING", "emb-1")
    assert has_critical_bindings(AGENT_ID, "RAG") is False
    bind_service(AGENT_ID, "VECTOR_DB", "vdb-1")
    assert has_critical_bindings(AGENT_ID, "RAG") is True


def test_has_critical_bindings_code_exec() -> None:
    assert has_critical_bindings(AGENT_ID, "CODE_EXEC") is False
    bind_service(AGENT_ID, "CODE_SANDBOX", "sb-1")
    assert has_critical_bindings(AGENT_ID, "CODE_EXEC") is True


def test_has_critical_bindings_unknown_type() -> None:
    # Unknown agent types have no critical requirements — always True
    assert has_critical_bindings(AGENT_ID, "CUSTOM_FOO") is True


def test_has_critical_bindings_unbound_not_counted() -> None:
    bind_service(AGENT_ID, "LLM", "svc-1")
    assert has_critical_bindings(AGENT_ID, "LLM") is True
    unbind_service(AGENT_ID, "LLM", "svc-1")
    assert has_critical_bindings(AGENT_ID, "LLM") is False

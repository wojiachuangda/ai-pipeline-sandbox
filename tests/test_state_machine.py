"""Tests for agent state machine: transitions, validation, binding checks."""

from __future__ import annotations

import pytest

from sandbox_app.state_machine import (
    _reset_store,
    get_status,
    is_valid_transition,
    register_agent,
    transition_status,
)
from sandbox_app.service_binding import _reset_store as _reset_bindings

AGENT_ID = "agent-sm-001"
AGENT_TYPE_LLM = "LLM"


@pytest.fixture(autouse=True)
def _clear_stores() -> None:
    _reset_store()
    _reset_bindings()


# ---------------------------------------------------------------------------
# pure transition checks
# ---------------------------------------------------------------------------


def test_valid_transitions() -> None:
    assert is_valid_transition("INACTIVE", "ACTIVE") is True
    assert is_valid_transition("ACTIVE", "INACTIVE") is True
    assert is_valid_transition("ACTIVE", "DEPRECATED") is True


def test_invalid_transition_inactive_to_deprecated() -> None:
    assert is_valid_transition("INACTIVE", "DEPRECATED") is False


def test_invalid_transition_deprecated_to_anything() -> None:
    for target in ("ACTIVE", "INACTIVE", "DEPRECATED"):
        assert is_valid_transition("DEPRECATED", target) is False


# ---------------------------------------------------------------------------
# transition_status — happy paths
# ---------------------------------------------------------------------------


def test_transition_inactive_to_active_with_bindings() -> None:
    from sandbox_app.service_binding import bind_service

    register_agent(AGENT_ID, AGENT_TYPE_LLM)
    bind_service(AGENT_ID, "LLM", "svc-1")

    result = transition_status(AGENT_ID, "ACTIVE", "activating", agent_type=AGENT_TYPE_LLM)
    assert result["current_status"] == "ACTIVE"
    assert result["approval_required"] is True  # ACTIVATE action triggers mock approval
    assert get_status(AGENT_ID) == "ACTIVE"


def test_transition_active_to_inactive() -> None:
    register_agent(AGENT_ID, AGENT_TYPE_LLM, initial_status="ACTIVE")
    result = transition_status(AGENT_ID, "INACTIVE", "deactivating")
    assert result["current_status"] == "INACTIVE"
    assert result["approval_required"] is False  # INACTIVE is not a sensitive action


def test_transition_active_to_deprecated() -> None:
    register_agent(AGENT_ID, AGENT_TYPE_LLM, initial_status="ACTIVE")
    result = transition_status(AGENT_ID, "DEPRECATED", "end of life")
    assert result["current_status"] == "DEPRECATED"
    assert result["approval_required"] is True  # DEPRECATE action triggers mock approval


# ---------------------------------------------------------------------------
# transition_status — error paths
# ---------------------------------------------------------------------------


def test_activate_without_critical_binding() -> None:
    register_agent(AGENT_ID, "RAG")  # RAG requires LLM + EMBEDDING + VECTOR_DB
    with pytest.raises(ValueError, match="MISSING_REQUIRED_BINDING"):
        transition_status(AGENT_ID, "ACTIVE", agent_type="RAG")


def test_activate_with_partial_bindings() -> None:
    from sandbox_app.service_binding import bind_service

    register_agent(AGENT_ID, "RAG")
    bind_service(AGENT_ID, "LLM", "llm-1")
    # Missing EMBEDDING and VECTOR_DB
    with pytest.raises(ValueError, match="MISSING_REQUIRED_BINDING"):
        transition_status(AGENT_ID, "ACTIVE", agent_type="RAG")


def test_invalid_transition_raises() -> None:
    register_agent(AGENT_ID, AGENT_TYPE_LLM)
    with pytest.raises(ValueError, match="INVALID_STATUS_TRANSITION"):
        transition_status(AGENT_ID, "DEPRECATED")


def test_deprecated_cannot_transition() -> None:
    register_agent(AGENT_ID, AGENT_TYPE_LLM, initial_status="DEPRECATED")
    with pytest.raises(ValueError, match="INVALID_STATUS_TRANSITION"):
        transition_status(AGENT_ID, "ACTIVE")
    with pytest.raises(ValueError, match="INVALID_STATUS_TRANSITION"):
        transition_status(AGENT_ID, "INACTIVE")


# ---------------------------------------------------------------------------
# unknown agent
# ---------------------------------------------------------------------------


def test_get_status_unknown_agent() -> None:
    assert get_status("nonexistent") == "INACTIVE"

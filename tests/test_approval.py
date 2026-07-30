"""Tests for the mock approval engine."""

from __future__ import annotations

from sandbox_app.approval import check_approval_required


def test_approval_required_for_activate() -> None:
    result = check_approval_required("ACTIVATE", "agent-1")
    assert result["approval_required"] is True
    assert result["status"] == "PENDING"
    assert "approval_id" in result


def test_approval_required_for_deprecate() -> None:
    result = check_approval_required("DEPRECATE", "agent-1")
    assert result["approval_required"] is True
    assert result["status"] == "PENDING"


def test_approval_not_required_for_other_actions() -> None:
    for action in ("BIND", "UNBIND", "CONFIGURE", "ROLLBACK", "CREATE_VERSION"):
        result = check_approval_required(action, "agent-1")
        assert result["approval_required"] is False, f"action={action} should not require approval"


def test_approval_ids_are_unique() -> None:
    """Each approval request should get a unique mock approval ID."""
    ids = {check_approval_required("ACTIVATE", f"agent-{i}")["approval_id"] for i in range(10)}
    assert len(ids) == 10

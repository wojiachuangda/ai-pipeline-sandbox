"""Mock approval engine — always returns a mock result, no real approval backend."""

from __future__ import annotations

import uuid

_APPROVAL_ACTIONS = {"ACTIVATE", "DEPRECATE"}


def check_approval_required(action: str, agent_id: str) -> dict:
    """Return a mock approval check for the given action.

    Args:
        action: The action being performed (e.g. ACTIVATE, DEPRECATE, BIND).
        agent_id: The agent identifier.

    Returns:
        dict with ``approval_required``, ``approval_id``, and ``status`` fields.
    """
    if action in _APPROVAL_ACTIONS:
        return {
            "approval_required": True,
            "approval_id": f"mock-{uuid.uuid4().hex[:12]}",
            "status": "PENDING",
        }
    return {"approval_required": False}

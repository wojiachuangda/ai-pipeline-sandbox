"""Agent status state machine with transition validation and binding checks.

Valid transitions:  INACTIVE ↔ ACTIVE,  ACTIVE → DEPRECATED (terminal).

Pure in-memory implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import approval
from .models import StatusTransition

# ---------------------------------------------------------------------------
# in-memory stores
# ---------------------------------------------------------------------------
_agent_states: dict[str, str] = {}  # agent_id → status
_agent_types: dict[str, str] = {}  # agent_id → agent_type
_transitions: dict[str, list[StatusTransition]] = {}  # agent_id → history

# ---------------------------------------------------------------------------
# valid transition map
# ---------------------------------------------------------------------------
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "INACTIVE": {"ACTIVE"},
    "ACTIVE": {"INACTIVE", "DEPRECATED"},
    "DEPRECATED": set(),  # terminal — no outgoing transitions
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """Pure function — is *to_status* reachable from *from_status*?"""
    return to_status in _VALID_TRANSITIONS.get(from_status, set())


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def register_agent(agent_id: str, agent_type: str, initial_status: str = "INACTIVE") -> None:
    """Register an agent's type and initial status with the state machine."""
    _agent_states[agent_id] = initial_status
    _agent_types[agent_id] = agent_type


def get_status(agent_id: str) -> str:
    """Return the current status string for *agent_id*.

    Returns ``"INACTIVE"`` for unknown agents (safe default).
    """
    return _agent_states.get(agent_id, "INACTIVE")


def transition_status(
    agent_id: str,
    target_status: str,
    reason: str = "",
    *,
    agent_type: str = "",
) -> dict:
    """Attempt to transition *agent_id* to *target_status*.

    Args:
        agent_id: The agent to transition.
        target_status: Desired status.
        reason: Human-readable reason for the transition.
        agent_type: Agent type used for binding validation on INACTIVE→ACTIVE.
                    If omitted, falls back to the type registered via ``register_agent``.

    Returns:
        ``{"agent_id", "current_status", "updated_at", "approval_required"}``

    Raises:
        ValueError: ``INVALID_STATUS_TRANSITION`` or ``MISSING_REQUIRED_BINDING``.
    """
    from .service_binding import has_critical_bindings

    agent_type = agent_type or _agent_types.get(agent_id, "")
    current = get_status(agent_id)

    if not is_valid_transition(current, target_status):
        raise ValueError(
            f"INVALID_STATUS_TRANSITION: cannot transition from {current} to {target_status}"
        )

    # Gate: INACTIVE → ACTIVE requires critical bindings
    if current == "INACTIVE" and target_status == "ACTIVE":
        if agent_type and not has_critical_bindings(agent_id, agent_type):
            raise ValueError(
                "MISSING_REQUIRED_BINDING: agent must have all critical services bound before activation"
            )

    # Record the transition
    record = StatusTransition(
        from_status=current,
        to_status=target_status,
        timestamp=datetime.now(timezone.utc),
        reason=reason,
    )
    _transitions.setdefault(agent_id, []).append(record)

    # Update state
    _agent_states[agent_id] = target_status
    _agent_types[agent_id] = agent_type or _agent_types.get(agent_id, "")

    # Approval check — map status to action: ACTIVE→ACTIVATE, DEPRECATED→DEPRECATE
    _status_to_action = {"ACTIVE": "ACTIVATE", "DEPRECATED": "DEPRECATE"}
    action = _status_to_action.get(target_status, target_status)
    approval_result = approval.check_approval_required(action, agent_id)

    return {
        "agent_id": agent_id,
        "current_status": target_status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "approval_required": approval_result.get("approval_required", False),
    }


# ---------------------------------------------------------------------------
# testing helpers
# ---------------------------------------------------------------------------


def _reset_store() -> None:
    """Clear all state-machine data (test-only)."""
    _agent_states.clear()
    _agent_types.clear()
    _transitions.clear()

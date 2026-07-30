"""Service binding — BIND/UNBIND with critical-service enforcement.

Pure in-memory implementation.
"""

from __future__ import annotations

from .models import ServiceBinding

# ---------------------------------------------------------------------------
# in-memory store  (keyed by (agent_id, service_type, service_instance_id))
# ---------------------------------------------------------------------------
_bindings: dict[tuple[str, str, str], ServiceBinding] = {}

# ---------------------------------------------------------------------------
# critical service map  — what each agent_type MUST have bound to go ACTIVE
# ---------------------------------------------------------------------------
CRITICAL_SERVICE_MAP: dict[str, list[str]] = {
    "LLM": ["LLM"],
    "RAG": ["LLM", "EMBEDDING", "VECTOR_DB"],
    "CODE_EXEC": ["CODE_SANDBOX"],
}


def _critical_types_for(agent_type: str) -> list[str]:
    """Return the list of service types that *agent_type* must have bound."""
    return CRITICAL_SERVICE_MAP.get(agent_type, [])


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def bind_service(
    agent_id: str,
    service_type: str,
    service_instance_id: str,
    binding_config: dict | None = None,
) -> ServiceBinding:
    """Create or update a binding to status=BOUND.

    Returns the binding record.
    """
    key = (agent_id, service_type, service_instance_id)
    binding = ServiceBinding(
        agent_id=agent_id,
        service_type=service_type,
        service_instance_id=service_instance_id,
        binding_config=binding_config if binding_config is not None else {},
        status="BOUND",
    )
    _bindings[key] = binding
    return binding


def unbind_service(
    agent_id: str,
    service_type: str,
    service_instance_id: str,
    *,
    agent_status: str = "INACTIVE",
    agent_type: str = "",
) -> ServiceBinding:
    """Mark a binding as UNBOUND.

    Args:
        agent_id: Owning agent.
        service_type: The type of service being unbound.
        service_instance_id: The specific instance.
        agent_status: Current agent status — if ACTIVE and service is critical, reject.
        agent_type: Agent type used to look up critical-service requirements.

    Returns:
        The updated binding with ``status="UNBOUND"``.

    Raises:
        ValueError: ``CRITICAL_SERVICE_IN_USE`` when active agent tries to unbind a critical service.
    """
    if agent_status == "ACTIVE" and service_type in _critical_types_for(agent_type):
        raise ValueError("CRITICAL_SERVICE_IN_USE: cannot unbind critical service while agent is ACTIVE")

    key = (agent_id, service_type, service_instance_id)
    existing = _bindings.get(key)
    if existing is None:
        # Create a new UNBOUND record so there's always a return value
        binding = ServiceBinding(
            agent_id=agent_id,
            service_type=service_type,
            service_instance_id=service_instance_id,
            status="UNBOUND",
        )
        _bindings[key] = binding
        return binding

    existing.status = "UNBOUND"
    return existing


def get_bindings(agent_id: str) -> list[ServiceBinding]:
    """Return all bindings (BOUND and UNBOUND) for an agent."""
    return [b for (aid, _st, _si), b in _bindings.items() if aid == agent_id]


def has_critical_bindings(agent_id: str, agent_type: str) -> bool:
    """Check whether *agent_id* has every required critical service type BOUND.

    Agents with no critical requirements (unknown/other types) always return True.
    """
    required = _critical_types_for(agent_type)
    if not required:
        return True

    # Gather distinct service_types that are currently BOUND for this agent
    bound_types: set[str] = set()
    for (aid, st, _si), b in _bindings.items():
        if aid == agent_id and b.status == "BOUND":
            bound_types.add(st)

    return all(rt in bound_types for rt in required)


# ---------------------------------------------------------------------------
# testing helpers
# ---------------------------------------------------------------------------


def _reset_store() -> None:
    """Clear all stored bindings (test-only)."""
    _bindings.clear()

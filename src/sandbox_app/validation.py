"""Pure validation functions for node configuration and context size.

No I/O, no side effects — callers feed in data, callers decide what to do
with the returned error strings.
"""

from __future__ import annotations

from .nodes import CollabMode, ContextVar, NodeConfig, NodeType


def validate_node_config(nc: NodeConfig) -> list[str]:
    """Validate *nc* and return a list of error strings (empty = valid)."""
    errors: list[str] = []

    # ── agent-ref rules ──────────────────────────────────────────────
    if nc.type is NodeType.AGENT:
        if nc.agent_ref is None:
            errors.append("AGENT node requires agent_ref")
        elif nc.agent_ref.status != "ACTIVE":
            errors.append("Agent must be ACTIVE")
    else:
        if nc.agent_ref is not None:
            errors.append(
                f"{nc.type.value} node should not have agent_ref"
            )

    # ── collab-mode rules ────────────────────────────────────────────
    if nc.collab is CollabMode.CONSENSUS and nc.voting_nodes < 2:
        errors.append("CONSENSUS requires at least 2 voting nodes")

    return errors


def validate_context_size(
    vars: list[ContextVar], max_bytes: int
) -> str | None:
    """Return ``"CONTEXT_SIZE_EXCEEDED: …"`` if total serialised size
    of *vars* exceeds *max_bytes*, otherwise ``None``.

    Size is computed as ``len(key.encode()) + len(value.encode())``
    for each variable.
    """
    total = sum(len(v.key.encode()) + len(v.value.encode()) for v in vars)
    if total > max_bytes:
        return f"CONTEXT_SIZE_EXCEEDED: {total - max_bytes} bytes over limit"
    return None

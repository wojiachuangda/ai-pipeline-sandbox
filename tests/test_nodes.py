"""Tests for node types, collaboration modes, and context validation.

Coverage: acceptance criteria AC-1 through AC-5.
"""

from __future__ import annotations

from sandbox_app import (
    AgentRef,
    CollabMode,
    ContextScope,
    ContextVar,
    NodeConfig,
    NodeType,
    validate_context_size,
    validate_node_config,
)


# ═══════════════════════════════════════════════════════════════════════
# AC-1: node-type enumeration & config validation
# ═══════════════════════════════════════════════════════════════════════

def test_node_type_enum_all_values() -> None:
    """All five node types are defined and distinct."""
    values = {nt.value for nt in NodeType}
    assert values == {"AGENT", "CONDITION", "FOREACH", "PARALLEL_GATEWAY", "SUB_WORKFLOW"}
    assert len(set(NodeType)) == 5  # distinct members


def test_valid_node_config_passes() -> None:
    """A well-formed AGENT config returns zero errors."""
    nc = NodeConfig(
        type=NodeType.AGENT,
        agent_ref=AgentRef(id="bot-1", status="ACTIVE"),
    )
    assert validate_node_config(nc) == []


def test_non_agent_type_rejects_agent_ref() -> None:
    """CONDITION / FOREACH / etc. with agent_ref → error."""
    for nt in (NodeType.CONDITION, NodeType.FOREACH,
               NodeType.PARALLEL_GATEWAY, NodeType.SUB_WORKFLOW):
        nc = NodeConfig(type=nt, agent_ref=AgentRef(id="bot-1"))
        errors = validate_node_config(nc)
        assert any(
            "should not have agent_ref" in e for e in errors
        ), f"{nt.value} should reject agent_ref"


def test_valid_node_config_for_all_types() -> None:
    """Every node type passes validation with its canonical config."""
    # AGENT — needs agent_ref
    assert validate_node_config(
        NodeConfig(type=NodeType.AGENT, agent_ref=AgentRef(id="a1"))
    ) == []

    # Non-agent types — must NOT have agent_ref
    for nt in (NodeType.CONDITION, NodeType.FOREACH,
               NodeType.PARALLEL_GATEWAY, NodeType.SUB_WORKFLOW):
        assert validate_node_config(NodeConfig(type=nt)) == []


# ═══════════════════════════════════════════════════════════════════════
# AC-2: AGENT node agent-ref integrity checks
# ═══════════════════════════════════════════════════════════════════════

def test_agent_node_missing_ref() -> None:
    """AGENT without agent_ref → error."""
    nc = NodeConfig(type=NodeType.AGENT, agent_ref=None)
    errors = validate_node_config(nc)
    assert any("AGENT node requires agent_ref" in e for e in errors)


def test_agent_node_inactive_status() -> None:
    """agent_ref with status INACTIVE → error."""
    nc = NodeConfig(
        type=NodeType.AGENT,
        agent_ref=AgentRef(id="bot-2", status="INACTIVE"),
    )
    errors = validate_node_config(nc)
    assert any("Agent must be ACTIVE" in e for e in errors)


def test_agent_node_default_status_passes() -> None:
    """agent_ref with default (ACTIVE) status is valid."""
    nc = NodeConfig(
        type=NodeType.AGENT,
        agent_ref=AgentRef(id="bot-3"),  # no explicit status → "ACTIVE"
    )
    assert validate_node_config(nc) == []


# ═══════════════════════════════════════════════════════════════════════
# AC-3: collaboration-mode configuration
# ═══════════════════════════════════════════════════════════════════════

def test_collab_mode_all_values() -> None:
    """All four collaboration modes are defined."""
    values = {cm.value for cm in CollabMode}
    assert values == {"SEQUENTIAL", "PARALLEL", "CONSENSUS", "LOOP"}
    assert len(set(CollabMode)) == 4


def test_consensus_requires_two_voting_nodes() -> None:
    """CONSENSUS + voting_nodes=1 → error."""
    nc = NodeConfig(
        type=NodeType.AGENT,
        agent_ref=AgentRef(id="bot-1"),
        collab=CollabMode.CONSENSUS,
        voting_nodes=1,
    )
    errors = validate_node_config(nc)
    assert any("CONSENSUS requires at least 2 voting nodes" in e for e in errors)


def test_consensus_two_voting_nodes_passes() -> None:
    """CONSENSUS + voting_nodes=2 → OK."""
    nc = NodeConfig(
        type=NodeType.AGENT,
        agent_ref=AgentRef(id="bot-1"),
        collab=CollabMode.CONSENSUS,
        voting_nodes=2,
    )
    assert validate_node_config(nc) == []


def test_other_collab_modes_dont_require_voting() -> None:
    """SEQUENTIAL / PARALLEL / LOOP work with voting_nodes=0."""
    for mode in (CollabMode.SEQUENTIAL, CollabMode.PARALLEL, CollabMode.LOOP):
        nc = NodeConfig(
            type=NodeType.AGENT,
            agent_ref=AgentRef(id="bot-1"),
            collab=mode,
            voting_nodes=0,
        )
        assert validate_node_config(nc) == []


# ═══════════════════════════════════════════════════════════════════════
# AC-4: context variables & size enforcement
# ═══════════════════════════════════════════════════════════════════════

def test_context_scope_all_values() -> None:
    """GLOBAL, NODE, SESSION are all defined."""
    values = {cs.value for cs in ContextScope}
    assert values == {"GLOBAL", "NODE", "SESSION"}


def test_context_size_within_limit() -> None:
    """Small context vars within limit → no error."""
    vars = [
        ContextVar(scope=ContextScope.NODE, key="a", value="1"),
        ContextVar(scope=ContextScope.SESSION, key="b", value="2"),
    ]
    assert validate_context_size(vars, max_bytes=1024) is None


def test_context_size_exceeded_tiny_threshold() -> None:
    """Large context vars over tiny limit → CONTEXT_SIZE_EXCEEDED."""
    vars = [
        ContextVar(scope=ContextScope.GLOBAL, key="key-abc", value="val-xyz"),
    ]
    result = validate_context_size(vars, max_bytes=8)
    assert result is not None
    assert "CONTEXT_SIZE_EXCEEDED" in result
    assert "bytes over limit" in result


def test_context_size_empty_vars() -> None:
    """Empty var list never exceeds even a zero-byte limit."""
    assert validate_context_size([], max_bytes=0) is None


def test_context_size_exact_limit() -> None:
    """Total size exactly at limit is accepted (not exceeding)."""
    vars = [ContextVar(scope=ContextScope.NODE, key="ab", value="cd")]
    # key "ab" = 2 bytes, value "cd" = 2 bytes → total 4
    assert validate_context_size(vars, max_bytes=4) is None


# ═══════════════════════════════════════════════════════════════════════
# AC-5: aggregate error-path coverage (covered by AC-1–4 tests above;
#       this test exercises multiple errors simultaneously)
# ═══════════════════════════════════════════════════════════════════════

def test_multiple_validation_errors() -> None:
    """An invalid config can produce multiple errors at once."""
    nc = NodeConfig(
        type=NodeType.AGENT,
        agent_ref=None,                      # missing ref
        collab=CollabMode.CONSENSUS,
        voting_nodes=0,                      # consensus needs ≥2
    )
    errors = validate_node_config(nc)
    assert len(errors) >= 2
    assert any("AGENT node requires agent_ref" in e for e in errors)
    assert any("CONSENSUS requires at least 2 voting nodes" in e for e in errors)

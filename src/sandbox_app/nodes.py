"""Node-type definitions, collaboration modes, and context models.

Pure domain types — no I/O or side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class NodeType(str, Enum):
    """Valid node types for a workflow graph."""

    AGENT = "AGENT"
    CONDITION = "CONDITION"
    FOREACH = "FOREACH"
    PARALLEL_GATEWAY = "PARALLEL_GATEWAY"
    SUB_WORKFLOW = "SUB_WORKFLOW"


class CollabMode(str, Enum):
    """Collaboration strategies for multi-agent nodes."""

    SEQUENTIAL = "SEQUENTIAL"
    PARALLEL = "PARALLEL"
    CONSENSUS = "CONSENSUS"
    LOOP = "LOOP"


class ContextScope(str, Enum):
    """Scope tier for a context variable."""

    GLOBAL = "GLOBAL"
    NODE = "NODE"
    SESSION = "SESSION"


@dataclass
class AgentRef:
    """Reference to a registered agent with its current lifecycle status."""

    id: str
    status: str = "ACTIVE"


@dataclass
class ContextVar:
    """A named context variable scoped at a particular tier."""

    scope: ContextScope
    key: str
    value: str


@dataclass
class NodeConfig:
    """Workflow node configuration with type, agent, collab mode, and context."""

    type: NodeType
    agent_ref: AgentRef | None = None
    collab: CollabMode = CollabMode.SEQUENTIAL
    context_vars: list[ContextVar] = field(default_factory=list)
    max_context_size: int = 1_048_576  # bytes, default 1 MiB
    voting_nodes: int = 0

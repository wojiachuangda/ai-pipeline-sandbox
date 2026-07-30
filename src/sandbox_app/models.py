"""Domain data classes for Agent versioning, state machine, and service binding."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Agent:
    """Core agent entity."""

    agent_id: str
    name: str
    agent_type: str
    status: str = "INACTIVE"
    tenant_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgentVersion:
    """Snapshot of an agent's configuration at a point in time."""

    version_id: str
    agent_id: str
    version: str  # semver, e.g. "0.1.0"
    description: str
    config: dict  # snapshot: capabilities, tool bindings, knowledge bases, prompt templates
    created_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = False


@dataclass
class ServiceBinding:
    """Binding between an agent and a service instance."""

    agent_id: str
    service_type: str  # LLM, EMBEDDING, VECTOR_DB, CODE_SANDBOX, TOOL_GATEWAY
    service_instance_id: str
    binding_config: dict = field(default_factory=dict)
    status: str = "BOUND"  # BOUND or UNBOUND


@dataclass
class TrafficConfig:
    """Multi-version traffic routing / canary configuration."""

    config_id: str
    agent_id: str
    version_traffic: list[dict] = field(default_factory=list)  # [{version_id, weight}]
    enable_canary: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class StatusTransition:
    """Record of a status change for audit trail."""

    from_status: str
    to_status: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""

"""Data models for workflow execution engine."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class ExecutionStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class NodeStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class NodeDef:
    """Definition of a single AGENT node in a workflow."""

    id: str
    type: str = "AGENT"
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDef:
    """Definition of a complete workflow."""

    id: str
    nodes: list[NodeDef] = field(default_factory=list)
    concurrency_limit: int = 1


@dataclass
class NodeExecution:
    """Runtime record of a single node execution."""

    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    output: dict[str, Any] | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass
class Execution:
    """Runtime record of a full workflow execution."""

    id: str
    workflow_id: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    nodes: list[NodeExecution] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    final_output: dict[str, Any] | None = None


@dataclass
class Progress:
    """Summary of execution progress for status queries."""

    execution_id: str
    status: ExecutionStatus
    completed: int
    total: int
    nodes: list[NodeExecution] = field(default_factory=list)


@dataclass
class DryRunResult:
    """Result of a dry-run execution in FULL mode."""

    workflow_id: str
    node_executions: list[NodeExecution]
    final_output: dict[str, Any] | None = None

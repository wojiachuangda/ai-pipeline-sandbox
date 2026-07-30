"""Task domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .dependency import DependencyGraph
from .trigger import Trigger

TaskType = Literal["SYNC", "ASYNC", "SCHEDULED"]
TaskStatus = Literal["INITIALIZED", "PENDING", "RUNNING", "COMPLETED", "FAILED"]


@dataclass
class Task:
    """A task managed by the sandbox pipeline.

    Fields map directly to AC-1: task_id, agent_id, type, input_schema,
    and the returned status INITIALIZED.
    """

    task_id: str
    name: str
    type: TaskType
    agent_id: str
    input_schema: dict | None = None
    status: TaskStatus = "INITIALIZED"
    priority: int = 5
    trigger: Trigger | None = None
    dependencies: DependencyGraph = field(default_factory=DependencyGraph)
    created_at: float = 0.0
    updated_at: float = 0.0

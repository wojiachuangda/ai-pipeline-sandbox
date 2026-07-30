"""Domain model layer: enums, data classes, and error types for the task queue system."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────


class TaskLifecycleStatus(StrEnum):
    """Lifecycle states for a task execution (AC-3)."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SchedulingPolicy(StrEnum):
    """Available scheduling strategies (AC-2).

    * PRIORITY_FIRST — highest priority first; FIFO within same priority (default).
    * ROUND_ROBIN  — cycle through priority groups round-robin.
    * WEIGHTED_RANDOM — placeholder (not implemented).
    * LEAST_LOAD       — placeholder (not implemented).
    """

    PRIORITY_FIRST = "PRIORITY_FIRST"
    ROUND_ROBIN = "ROUND_ROBIN"
    WEIGHTED_RANDOM = "WEIGHTED_RANDOM"
    LEAST_LOAD = "LEAST_LOAD"


# ── Data models ───────────────────────────────────────────────────────────────


class StatusTransition(BaseModel):
    """A single state transition record (AC-3)."""

    status: TaskLifecycleStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str = "system"
    detail: str = ""


class QueueEntry(BaseModel):
    """Represents a task waiting in or processed through the queue."""

    queue_entry_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    priority: int = 0
    position: int = -1
    status: TaskLifecycleStatus = TaskLifecycleStatus.QUEUED
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status_history: list[StatusTransition] = Field(default_factory=list)
    execution_params: dict[str, Any] = Field(default_factory=dict)


class EnqueueResponse(BaseModel):
    """Returned by POST /queue/enqueue (AC-1)."""

    queue_entry_id: uuid.UUID
    position: int
    estimated_start_time: datetime | None = None


class TimelineResponse(BaseModel):
    """Returned by GET /tasks/{task_id}/timeline (AC-3)."""

    execution_id: uuid.UUID
    status_history: list[StatusTransition]
    current_status: TaskLifecycleStatus | None = None
    total_duration_ms: float | None = None
    assigned_instance: str | None = None


# ── Error types ───────────────────────────────────────────────────────────────


class QueueFullError(Exception):
    """Raised when the queue has reached max_size (AC-5). Maps to HTTP 429."""

    def __init__(self, max_size: int, task_id: uuid.UUID | None = None) -> None:
        self.max_size = max_size
        self.task_id = task_id
        super().__init__(f"Queue is full (max_size={max_size})")


class DuplicateEnqueueError(Exception):
    """Raised when a task_id is already present in the queue (AC-1). Maps to HTTP 409."""

    def __init__(self, task_id: uuid.UUID, existing_entry_id: uuid.UUID) -> None:
        self.task_id = task_id
        self.existing_entry_id = existing_entry_id
        super().__init__(f"Task {task_id} is already enqueued as {existing_entry_id}")


class InvalidTransitionError(Exception):
    """Raised on illegal lifecycle state transitions (AC-3). Maps to HTTP 422."""

    def __init__(self, from_status: str, to_status: str, detail: str = "") -> None:
        self.from_status = from_status
        self.to_status = to_status
        self.detail = detail
        super().__init__(f"Cannot transition from {from_status} to {to_status}: {detail}")


# ── Transition table (AC-3) ──────────────────────────────────────────────────

VALID_TRANSITIONS: dict[TaskLifecycleStatus, set[TaskLifecycleStatus]] = {
    TaskLifecycleStatus.PENDING: {TaskLifecycleStatus.QUEUED, TaskLifecycleStatus.CANCELLED},
    TaskLifecycleStatus.QUEUED: {TaskLifecycleStatus.ASSIGNED, TaskLifecycleStatus.CANCELLED},
    TaskLifecycleStatus.ASSIGNED: {TaskLifecycleStatus.RUNNING, TaskLifecycleStatus.CANCELLED},
    TaskLifecycleStatus.RUNNING: {
        TaskLifecycleStatus.SUCCEEDED,
        TaskLifecycleStatus.FAILED,
        TaskLifecycleStatus.CANCELLED,
    },
    TaskLifecycleStatus.SUCCEEDED: set(),
    TaskLifecycleStatus.FAILED: set(),
    TaskLifecycleStatus.CANCELLED: set(),
}

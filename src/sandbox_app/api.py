"""FastAPI routes for queue management and task lifecycle (AC-1, AC-2, AC-3, AC-5)."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .domain import (
    TaskLifecycleStatus,
    SchedulingPolicy,
    EnqueueResponse,
    QueueEntry,
    TimelineResponse,
    QueueFullError,
    DuplicateEnqueueError,
    InvalidTransitionError,
)
from .queue import TaskQueue
from .lifecycle import LifecycleManager

# ── Application singleton ─────────────────────────────────────────────────

app = FastAPI(title="Sandbox Task Queue", version="0.1.0")
_queue = TaskQueue(max_size=10000, policy=SchedulingPolicy.PRIORITY_FIRST)
_lifecycle = _queue.lifecycle  # reuse the queue's lifecycle manager


# ── Request models ───────────────────────────────────────────────────────


class EnqueueRequest(BaseModel):
    task_id: uuid.UUID
    priority: int = 0
    execution_params: dict | None = None


class DequeueRequest(BaseModel):
    policy: SchedulingPolicy | None = None


class TransitionRequest(BaseModel):
    to_status: TaskLifecycleStatus
    actor: str = "api"
    detail: str = ""


# ── Error handlers ───────────────────────────────────────────────────────


@app.exception_handler(QueueFullError)
async def handle_queue_full(_request, exc: QueueFullError) -> dict:
    return {"error_code": "QUEUE_FULL", "detail": str(exc)}, 429  # type: ignore[return-value]


@app.exception_handler(DuplicateEnqueueError)
async def handle_duplicate(_request, exc: DuplicateEnqueueError) -> dict:
    return {"error_code": "DUPLICATE_TASK", "detail": str(exc)}, 409  # type: ignore[return-value]


@app.exception_handler(InvalidTransitionError)
async def handle_invalid_transition(_request, exc: InvalidTransitionError) -> dict:
    return {"detail": str(exc)}, 422  # type: ignore[return-value]


# ── Routes ───────────────────────────────────────────────────────────────


@app.post("/queue/enqueue", response_model=EnqueueResponse)
def enqueue(body: EnqueueRequest) -> EnqueueResponse:
    """Add a task to the queue (AC-1)."""
    return _queue.enqueue(
        task_id=body.task_id,
        priority=body.priority,
        execution_params=body.execution_params,
    )


@app.post("/queue/dequeue", response_model=QueueEntry)
def dequeue(body: DequeueRequest | None = None) -> QueueEntry:
    """Pop the next task from the queue (AC-2).

    Returns 404 when the queue is empty.
    """
    try:
        return _queue.dequeue(policy=body.policy if body else None)
    except IndexError:
        raise HTTPException(status_code=404, detail="Queue is empty")


@app.get("/queue/entry/{entry_id}", response_model=QueueEntry)
def get_queue_entry(entry_id: uuid.UUID) -> QueueEntry:
    """Retrieve a queue entry by its ID (AC-1)."""
    entry = _queue.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")
    return entry


@app.get("/tasks/{task_id}/timeline", response_model=TimelineResponse)
def get_timeline(task_id: uuid.UUID) -> TimelineResponse:
    """Return the lifecycle timeline for a task (AC-3)."""
    # Find the execution_id by looking through the queue's lifecycle entries.
    # task_id (business id) → queue_entry_id (execution id) mapping lives in the queue.
    entry = _queue.get_entry_by_id(task_id)

    if entry is None:
        # The queue may have already released it; check lifecycle directly
        # by iterating — fallback: try task_id as execution_id
        if not _lifecycle.entry_exists(task_id):
            raise HTTPException(status_code=404, detail=f"Timeline for task {task_id} not found")
        execution_id = task_id
        entry = None
    else:
        execution_id = entry.queue_entry_id

    timeline = _lifecycle.get_timeline(execution_id)
    current_status = _lifecycle.get_current_status(execution_id)
    duration_ms = _lifecycle.compute_duration_ms(execution_id)

    return TimelineResponse(
        execution_id=execution_id,
        status_history=timeline,
        current_status=current_status,
        total_duration_ms=duration_ms,
        assigned_instance=None,
    )


@app.post("/tasks/{task_id}/transition", response_model=TimelineResponse)
def trigger_transition(task_id: uuid.UUID, body: TransitionRequest) -> TimelineResponse:
    """Manually trigger a lifecycle state transition (AC-3, test/admin use)."""
    # Resolve execution_id
    entry = _queue.get_entry_by_id(task_id)

    if entry is None:
        if not _lifecycle.entry_exists(task_id):
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        execution_id = task_id
        current = _lifecycle.get_current_status(execution_id)
        if current is None:
            raise HTTPException(status_code=404, detail=f"No status for task {task_id}")
    else:
        execution_id = entry.queue_entry_id
        current = _lifecycle.get_current_status(execution_id)
        if current is None:
            current = TaskLifecycleStatus.QUEUED

    _lifecycle.record_transition(
        execution_id=execution_id,
        from_status=current,
        to_status=body.to_status,
        actor=body.actor,
        detail=body.detail,
    )

    timeline = _lifecycle.get_timeline(execution_id)
    new_status = _lifecycle.get_current_status(execution_id)
    duration_ms = _lifecycle.compute_duration_ms(execution_id)

    return TimelineResponse(
        execution_id=execution_id,
        status_history=timeline,
        current_status=new_status,
        total_duration_ms=duration_ms,
        assigned_instance=None,
    )


# ── Health (passthrough to existing core helpers) ────────────────────────


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ping")
def ping() -> dict:
    return {"pong": "true"}

"""Public API for task management — thin wrapper over store + domain models."""

from __future__ import annotations

import time
import uuid

from .dependency import CircularDependencyError, DependencyGraph, DependencyType, _has_cycle
from .store import _tasks, get, list_all, save
from .task import Task, TaskType
from .trigger import CronTrigger, EventTrigger


def _error(code: str, detail: str = "") -> dict:
    return {"code": code, "detail": detail}


def create_task(
    *,
    name: str,
    task_type: TaskType,
    agent_id: str,
    input_schema: dict | None = None,
    priority: int = 5,
    trigger: dict | None = None,
) -> dict:
    """Create a task and return its id + INITIALIZED status (AC-1)."""
    if task_type not in ("SYNC", "ASYNC", "SCHEDULED"):
        return _error("INVALID_TASK_TYPE", f"Got {task_type!r}")
    if not (1 <= priority <= 10):
        return _error("INVALID_PRIORITY", f"Priority {priority} not in 1–10")

    trigger_obj = None
    if trigger is not None:
        trigger_type = trigger.get("type")
        if trigger_type == "CRON":
            try:
                trigger_obj = CronTrigger(expression=trigger["expression"])
            except ValueError as exc:
                return _error("INVALID_CRON", str(exc))
        elif trigger_type == "EVENT":
            trigger_obj = EventTrigger(event_type=trigger["event_type"])
        # Unknown trigger types are silently ignored (no error code defined)

    now = time.time()
    task = Task(
        task_id=str(uuid.uuid4()),
        name=name,
        type=task_type,
        agent_id=agent_id,
        input_schema=input_schema,
        priority=priority,
        trigger=trigger_obj,
        created_at=now,
        updated_at=now,
    )
    save(task)
    return {"task_id": task.task_id, "status": task.status}


def update_priority(task_id: str, priority: int) -> dict:
    """Update task priority (AC-3)."""
    if not (1 <= priority <= 10):
        return _error("INVALID_PRIORITY", f"Priority {priority} not in 1–10")
    task = get(task_id)
    if task is None:
        return _error("TASK_NOT_FOUND", f"No task with id {task_id!r}")
    task.priority = priority
    task.updated_at = time.time()
    return {"task_id": task.task_id, "priority": task.priority}


def set_dependency(
    task_id: str,
    dep_type: DependencyType,
    depends_on: list[str],
) -> dict:
    """Set task dependencies with cycle detection (AC-4)."""
    if dep_type not in ("NONE", "SEQUENTIAL", "AND_PARALLEL", "OR_PARALLEL"):
        return _error("INVALID_DEPENDENCY_TYPE", f"Got {dep_type!r}")

    task = get(task_id)
    if task is None:
        return _error("TASK_NOT_FOUND", f"No task with id {task_id!r}")

    # Build adjacency dict for the full store to check for cycles
    adjacency: dict[str, list[str]] = {}
    for tid, t in _tasks.items():
        adjacency[tid] = list(t.dependencies.depends_on)
    # Apply proposed change
    adjacency[task_id] = list(depends_on)

    try:
        if _has_cycle(adjacency):
            # Find the actual cycle for the error message
            from .dependency import _find_cycle

            chain = _find_cycle(adjacency)
            raise CircularDependencyError(chain)
    except CircularDependencyError:
        return _error(
            "CIRCULAR_TASK_DEPENDENCY",
            f"Adding dependencies {depends_on} to {task_id} would create a cycle",
        )

    task.dependencies = DependencyGraph(type=dep_type, depends_on=list(depends_on))
    task.updated_at = time.time()
    return {"task_id": task.task_id, "dependencies": task.dependencies}


def get_task(task_id: str) -> dict | None:
    """Retrieve a single task by id."""
    task = get(task_id)
    if task is None:
        return None
    return _to_dict(task)


def list_tasks() -> list[dict]:
    """List all tasks."""
    return [_to_dict(t) for t in list_all()]


def _to_dict(task: Task) -> dict:
    result: dict = {
        "task_id": task.task_id,
        "name": task.name,
        "type": task.type,
        "agent_id": task.agent_id,
        "input_schema": task.input_schema,
        "status": task.status,
        "priority": task.priority,
        "dependencies": {
            "type": task.dependencies.type,
            "depends_on": task.dependencies.depends_on,
        },
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }
    if task.trigger is not None:
        if isinstance(task.trigger, CronTrigger):
            result["trigger"] = {"type": "CRON", "expression": task.trigger.expression}
        elif isinstance(task.trigger, EventTrigger):
            result["trigger"] = {"type": "EVENT", "event_type": task.trigger.event_type}
    return result

"""In-memory task store — minimal diff, zero external dependencies."""

from __future__ import annotations

from .task import Task

_tasks: dict[str, Task] = {}


def save(task: Task) -> None:
    _tasks[task.task_id] = task


def get(task_id: str) -> Task | None:
    return _tasks.get(task_id)


def list_all() -> list[Task]:
    return list(_tasks.values())


def reset() -> None:
    """Clear the store — for test isolation only."""
    _tasks.clear()

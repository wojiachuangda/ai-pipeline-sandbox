"""Tests for task creation, triggers, priority, and dependencies.

Covers AC-1 through AC-5 inclusive.
"""

import pytest

from sandbox_app import (
    CircularDependencyError,
    CronTrigger,
    DependencyGraph,
    EventTrigger,
    Task,
    create_task,
    get_task,
    list_tasks,
    set_dependency,
    update_priority,
    validate_cron,
)


# ---------------------------------------------------------------------------
# AC-1 — Task creation
# ---------------------------------------------------------------------------

def test_create_sync_task() -> None:
    result = create_task(name="sync-1", task_type="SYNC", agent_id="agent-42")
    assert "task_id" in result
    assert result["status"] == "INITIALIZED"
    # Verify stored data
    stored = get_task(result["task_id"])
    assert stored is not None
    assert stored["type"] == "SYNC"
    assert stored["name"] == "sync-1"
    assert stored["agent_id"] == "agent-42"


def test_create_async_task() -> None:
    schema = {"steps": "int"}
    result = create_task(
        name="async-1", task_type="ASYNC", agent_id="agent-7", input_schema=schema
    )
    assert result["status"] == "INITIALIZED"
    stored = get_task(result["task_id"])
    assert stored is not None
    assert stored["type"] == "ASYNC"
    assert stored["input_schema"] == schema


def test_create_scheduled_task_with_cron() -> None:
    result = create_task(
        name="sched-1",
        task_type="SCHEDULED",
        agent_id="agent-cron",
        trigger={"type": "CRON", "expression": "*/5 * * * *"},
    )
    assert result["status"] == "INITIALIZED"
    stored = get_task(result["task_id"])
    assert stored is not None
    assert stored["type"] == "SCHEDULED"
    assert stored["trigger"] == {"type": "CRON", "expression": "*/5 * * * *"}


# ---------------------------------------------------------------------------
# AC-2 — Triggers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "expression",
    [
        "*/5 * * * *",
        "0 0 * * *",
        "59 23 31 12 6",
        "0 9 * * 1-5",
        "* * * * *",
    ],
)
def test_valid_cron_expressions(expression: str) -> None:
    """All standard 5-field cron expressions should validate."""
    validate_cron(expression)  # does not raise


@pytest.mark.parametrize(
    "expression",
    [
        "*/5 * * *",          # 4 fields
        "* * * * * *",        # 6 fields
        "abc * * * *",        # non-numeric token
        "*/5 * * * * extra",  # trailing text
        "",                    # empty
        "   ",                 # whitespace only
    ],
)
def test_invalid_cron_rejected(expression: str) -> None:
    """Invalid cron expressions → INVALID_CRON (AC-2)."""
    result = create_task(
        name="bad-cron",
        task_type="SCHEDULED",
        agent_id="agent-1",
        trigger={"type": "CRON", "expression": expression},
    )
    assert result["code"] == "INVALID_CRON"


def test_event_trigger() -> None:
    result = create_task(
        name="event-task",
        task_type="ASYNC",
        agent_id="agent-evt",
        trigger={"type": "EVENT", "event_type": "file.uploaded"},
    )
    stored = get_task(result["task_id"])
    assert stored is not None
    assert stored["trigger"] == {"type": "EVENT", "event_type": "file.uploaded"}


def test_cron_trigger_dataclass_rejects_bad() -> None:
    with pytest.raises(ValueError):
        CronTrigger(expression="not valid")


def test_event_trigger_dataclass() -> None:
    et = EventTrigger(event_type="task.done")
    assert et.event_type == "task.done"


# ---------------------------------------------------------------------------
# AC-3 — Priority
# ---------------------------------------------------------------------------

def test_priority_default() -> None:
    result = create_task(name="pri-default", task_type="SYNC", agent_id="a")
    stored = get_task(result["task_id"])
    assert stored is not None
    assert stored["priority"] == 5


def test_priority_boundary_low() -> None:
    result = create_task(name="pri-1", task_type="SYNC", agent_id="a", priority=1)
    stored = get_task(result["task_id"])
    assert stored is not None
    assert stored["priority"] == 1


def test_priority_boundary_high() -> None:
    result = create_task(name="pri-10", task_type="SYNC", agent_id="a", priority=10)
    stored = get_task(result["task_id"])
    assert stored is not None
    assert stored["priority"] == 10


def test_priority_update() -> None:
    result = create_task(name="pri-upd", task_type="SYNC", agent_id="a")
    update_result = update_priority(result["task_id"], 8)
    assert update_result["priority"] == 8
    stored = get_task(result["task_id"])
    assert stored is not None
    assert stored["priority"] == 8


@pytest.mark.parametrize("bad_priority", [0, 11, -1, 100])
def test_priority_out_of_range_on_create(bad_priority: int) -> None:
    result = create_task(
        name="bad-pri", task_type="SYNC", agent_id="a", priority=bad_priority
    )
    assert result["code"] == "INVALID_PRIORITY"


@pytest.mark.parametrize("bad_priority", [0, 11, -1, 100])
def test_priority_out_of_range_on_update(bad_priority: int) -> None:
    result = create_task(name="to-update", task_type="SYNC", agent_id="a")
    update_result = update_priority(result["task_id"], bad_priority)
    assert update_result["code"] == "INVALID_PRIORITY"


# ---------------------------------------------------------------------------
# AC-4 — Dependencies
# ---------------------------------------------------------------------------

def test_sequential_dependency() -> None:
    a = create_task(name="A", task_type="SYNC", agent_id="x")
    b = create_task(name="B", task_type="SYNC", agent_id="x")
    dep_result = set_dependency(b["task_id"], "SEQUENTIAL", [a["task_id"]])
    assert dep_result["task_id"] == b["task_id"]
    assert dep_result["dependencies"].type == "SEQUENTIAL"
    assert dep_result["dependencies"].depends_on == [a["task_id"]]


def test_and_parallel_dependency() -> None:
    a = create_task(name="A", task_type="SYNC", agent_id="x")
    b = create_task(name="B", task_type="SYNC", agent_id="x")
    c = create_task(name="C", task_type="SYNC", agent_id="x")
    dep_result = set_dependency(c["task_id"], "AND_PARALLEL", [a["task_id"], b["task_id"]])
    assert dep_result["dependencies"].type == "AND_PARALLEL"
    assert dep_result["dependencies"].depends_on == [a["task_id"], b["task_id"]]


def test_or_parallel_dependency() -> None:
    a = create_task(name="A", task_type="SYNC", agent_id="x")
    b = create_task(name="B", task_type="SYNC", agent_id="x")
    dep_result = set_dependency(b["task_id"], "OR_PARALLEL", [a["task_id"]])
    assert dep_result["dependencies"].type == "OR_PARALLEL"


def test_circular_dependency_detected_direct() -> None:
    """A → B → A → CIRCULAR_TASK_DEPENDENCY."""
    a = create_task(name="circle-A", task_type="SYNC", agent_id="x")
    b = create_task(name="circle-B", task_type="SYNC", agent_id="x")
    set_dependency(b["task_id"], "SEQUENTIAL", [a["task_id"]])
    result = set_dependency(a["task_id"], "SEQUENTIAL", [b["task_id"]])
    assert result["code"] == "CIRCULAR_TASK_DEPENDENCY"


def test_complex_circular_chain() -> None:
    """A → B → C → A  three-node cycle."""
    a = create_task(name="A", task_type="SYNC", agent_id="x")
    b = create_task(name="B", task_type="SYNC", agent_id="x")
    c = create_task(name="C", task_type="SYNC", agent_id="x")
    set_dependency(b["task_id"], "SEQUENTIAL", [a["task_id"]])
    set_dependency(c["task_id"], "SEQUENTIAL", [b["task_id"]])
    result = set_dependency(a["task_id"], "SEQUENTIAL", [c["task_id"]])
    assert result["code"] == "CIRCULAR_TASK_DEPENDENCY"


def test_self_dependency_is_cycle() -> None:
    """A → A is a direct self-cycle."""
    a = create_task(name="self-dep", task_type="SYNC", agent_id="x")
    result = set_dependency(a["task_id"], "SEQUENTIAL", [a["task_id"]])
    assert result["code"] == "CIRCULAR_TASK_DEPENDENCY"


def test_none_dependency_type() -> None:
    """Clearing dependencies with NONE type should work."""
    a = create_task(name="A", task_type="SYNC", agent_id="x")
    result = set_dependency(a["task_id"], "NONE", [])
    assert result["dependencies"].type == "NONE"
    assert result["dependencies"].depends_on == []


# ---------------------------------------------------------------------------
# Error edge-cases
# ---------------------------------------------------------------------------

def test_invalid_task_type() -> None:
    result = create_task(name="bad", task_type="BATCH", agent_id="x")  # type: ignore[arg-type]
    assert result["code"] == "INVALID_TASK_TYPE"


def test_task_not_found_update_priority() -> None:
    result = update_priority("nonexistent-id", 5)
    assert result["code"] == "TASK_NOT_FOUND"


def test_task_not_found_set_dependency() -> None:
    result = set_dependency("nonexistent-id", "SEQUENTIAL", ["other"])
    assert result["code"] == "TASK_NOT_FOUND"


def test_invalid_dependency_type() -> None:
    a = create_task(name="A", task_type="SYNC", agent_id="x")
    result = set_dependency(a["task_id"], "FAN_OUT", [])  # type: ignore[arg-type]
    assert result["code"] == "INVALID_DEPENDENCY_TYPE"


# ---------------------------------------------------------------------------
# Utility / model tests
# ---------------------------------------------------------------------------

def test_task_dataclass_defaults() -> None:
    t = Task(task_id="t1", name="test", type="SYNC", agent_id="a1")
    assert t.status == "INITIALIZED"
    assert t.priority == 5
    assert t.trigger is None
    assert t.dependencies.type == "NONE"
    assert t.dependencies.depends_on == []


def test_dependency_graph_defaults() -> None:
    dg = DependencyGraph()
    assert dg.type == "NONE"
    assert dg.depends_on == []


def test_list_tasks() -> None:
    # Create a few tasks and verify list
    create_task(name="lt-1", task_type="SYNC", agent_id="x")
    create_task(name="lt-2", task_type="ASYNC", agent_id="x")
    all_tasks = list_tasks()
    names = {t["name"] for t in all_tasks}
    assert "lt-1" in names
    assert "lt-2" in names


def test_circular_dependency_error_contains_chain() -> None:
    """The exception itself carries the cycle chain."""
    err = CircularDependencyError(["A", "B", "A"])
    assert err.chain == ["A", "B", "A"]
    assert "A -> B -> A" in str(err)

"""Tests for the workflow execution engine.

Covers AC-1 through AC-4, AC-6, and AC-7.
"""

from __future__ import annotations

import time
from unittest import mock

import pytest

from sandbox_app import (
    config,
    dry_run,
    engine,
    get_concurrency_limit,
    get_progress,
    get_status,
    run_sync,
    trigger,
)
from sandbox_app.models import (
    DryRunResult,
    ExecutionStatus,
    NodeDef,
    NodeStatus,
    WorkflowDef,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow(
    wf_id: str = "wf-test",
    node_ids: tuple[str, ...] = ("node-a", "node-b", "node-c"),
) -> WorkflowDef:
    """Build a minimal workflow with simple AGENT nodes."""
    nodes = [NodeDef(id=nid) for nid in node_ids]
    return WorkflowDef(id=wf_id, nodes=nodes)


# ---------------------------------------------------------------------------
# AC-1: trigger returns execution_id immediately (async default)
# ---------------------------------------------------------------------------


def test_trigger_returns_execution_id() -> None:
    """trigger() must return a non-empty execution_id string."""
    wf = _make_workflow()
    eid = trigger(wf)
    assert isinstance(eid, str)
    assert eid.startswith("exec-")
    assert len(eid) > len("exec-")


def test_trigger_async_default() -> None:
    """After trigger() returns, execution status is *not* COMPLETED yet."""
    wf = _make_workflow(node_ids=("slow",))
    eid = trigger(wf)

    # The background thread should not have finished yet — status is
    # either pending or running, never completed on return.
    status = get_status(eid)
    assert status is not None
    assert status != ExecutionStatus.COMPLETED

    # Wait for the background execution to settle, then verify it did
    # eventually finish.
    _wait_for_execution(eid)
    assert get_status(eid) == ExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# AC-2: sequential AGENT node execution (stub agent runner)
# ---------------------------------------------------------------------------


def test_sequential_node_execution() -> None:
    """Nodes execute in definition order; each produces stub output."""
    wf = _make_workflow(node_ids=("first", "second", "third"))
    eid = trigger(wf)
    _wait_for_execution(eid, timeout=3.0)

    progress = get_progress(eid)
    assert progress is not None
    assert progress.status == ExecutionStatus.COMPLETED
    assert progress.completed == 3
    assert progress.total == 3

    # Verify each node succeeded and produced expected stub output.
    for node_exec in progress.nodes:
        assert node_exec.status == NodeStatus.COMPLETED
        assert node_exec.output is not None
        assert node_exec.output["node_id"] == node_exec.node_id
        assert "stub output" in node_exec.output["result"]

    # Verify execution order: started_at timestamps must be monotonic.
    timestamps = [n.started_at for n in progress.nodes]
    assert timestamps == sorted(timestamps), "Nodes should execute in definition order"


def test_node_failure_stops_execution() -> None:
    """A failing node sets execution status to FAILED; later nodes do not run."""
    wf = _make_workflow(node_ids=("ok", "bad", "never-runs"))

    # Make the stub runner fail for the second node.
    original = engine.stub_agent_runner

    def _failing_runner(node_id: str) -> dict:
        if node_id == "bad":
            raise RuntimeError("simulated agent crash")
        return original(node_id)

    with mock.patch.object(engine, "stub_agent_runner", side_effect=_failing_runner):
        eid = trigger(wf)
        _wait_for_execution(eid, timeout=3.0)

    progress = get_progress(eid)
    assert progress is not None
    assert progress.status == ExecutionStatus.FAILED
    assert progress.completed == 2  # "ok" completed, "bad" failed

    # The failing node must carry the error.
    bad_node = next(n for n in progress.nodes if n.node_id == "bad")
    assert bad_node.status == NodeStatus.FAILED
    assert bad_node.error is not None
    assert "simulated agent crash" in bad_node.error

    # The third node must still be pending (never started).
    never_node = next(n for n in progress.nodes if n.node_id == "never-runs")
    assert never_node.status == NodeStatus.PENDING


# ---------------------------------------------------------------------------
# AC-3: dry-run FULL returns node_executions and final_output
# ---------------------------------------------------------------------------


def test_dry_run_full_returns_executions() -> None:
    """dry_run(mode='FULL') must return complete trace + final_output."""
    wf = _make_workflow(node_ids=("d1", "d2"))
    result = dry_run(wf, mode="FULL")

    assert isinstance(result, DryRunResult)
    assert result.workflow_id == wf.id
    assert len(result.node_executions) == 2

    for ne in result.node_executions:
        assert ne.status == NodeStatus.COMPLETED
        assert ne.output is not None
        assert ne.output["node_id"] == ne.node_id

    # final_output maps each node_id → its output dict.
    assert result.final_output is not None
    assert set(result.final_output.keys()) == {"d1", "d2"}


def test_dry_run_full_stops_on_failure() -> None:
    """dry_run(FULL) stops at the first failing node and returns partial trace."""
    wf = _make_workflow(node_ids=("d1", "bad", "d3"))
    original = engine.stub_agent_runner

    def _failing(node_id: str) -> dict:
        if node_id == "bad":
            raise RuntimeError("boom")
        return original(node_id)

    with mock.patch.object(engine, "stub_agent_runner", side_effect=_failing):
        result = dry_run(wf, mode="FULL")

    assert len(result.node_executions) == 2  # d1 ok, bad failed — d3 never ran
    assert result.node_executions[0].node_id == "d1"
    assert result.node_executions[0].status == NodeStatus.COMPLETED
    assert result.node_executions[1].node_id == "bad"
    assert result.node_executions[1].status == NodeStatus.FAILED


def test_dry_run_rejects_unknown_mode() -> None:
    """Only 'FULL' mode is supported; anything else raises ValueError."""
    wf = _make_workflow()
    with pytest.raises(ValueError, match="Unsupported dry_run mode"):
        dry_run(wf, mode="PARTIAL")


# ---------------------------------------------------------------------------
# AC-4: execution status query — get_status / get_progress
# ---------------------------------------------------------------------------


def test_get_status_returns_none_for_unknown_id() -> None:
    assert get_status("nonexistent-id") is None


def test_get_progress_returns_none_for_unknown_id() -> None:
    assert get_progress("nonexistent-id") is None


def test_get_status_and_progress_during_lifecycle() -> None:
    """get_status / get_progress reflect state transitions over time."""
    wf = _make_workflow(node_ids=("a",))
    eid = trigger(wf)

    # Immediately after trigger.
    assert get_status(eid) in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING)

    _wait_for_execution(eid, timeout=3.0)

    # After completion.
    assert get_status(eid) == ExecutionStatus.COMPLETED
    progress = get_progress(eid)
    assert progress is not None
    assert progress.completed == 1
    assert progress.total == 1
    assert progress.nodes[0].status == NodeStatus.COMPLETED
    assert progress.nodes[0].started_at is not None
    assert progress.nodes[0].finished_at is not None


# ---------------------------------------------------------------------------
# AC-6: concurrency limit is configurable and readable
# ---------------------------------------------------------------------------


def test_concurrency_limit_configurable() -> None:
    """WORKFLOW_CONCURRENCY_LIMIT can be read at runtime."""
    original = config.WORKFLOW_CONCURRENCY_LIMIT
    try:
        config.WORKFLOW_CONCURRENCY_LIMIT = 3
        assert get_concurrency_limit() == 3
    finally:
        config.WORKFLOW_CONCURRENCY_LIMIT = original


def test_concurrency_limit_default_is_one() -> None:
    """MVP default concurrency limit is 1."""
    # Reset to default for a clean read.
    saved = config.WORKFLOW_CONCURRENCY_LIMIT
    config.WORKFLOW_CONCURRENCY_LIMIT = 1
    try:
        assert get_concurrency_limit() == 1
    finally:
        config.WORKFLOW_CONCURRENCY_LIMIT = saved


def test_concurrency_limit_returned_as_int() -> None:
    """get_concurrency_limit always returns an int."""
    assert isinstance(get_concurrency_limit(), int)


# ---------------------------------------------------------------------------
# AC-7: additional coverage — run_sync direct call
# ---------------------------------------------------------------------------


def test_run_sync_completes_all_nodes() -> None:
    """Calling run_sync directly must execute all nodes and return completed Execution."""
    from sandbox_app.engine import _create_execution, _store

    wf = _make_workflow(node_ids=("x", "y"))
    execution = _create_execution(wf)
    _store[execution.id] = execution

    result = run_sync(execution.id)
    assert result.status == ExecutionStatus.COMPLETED
    assert len(result.nodes) == 2
    assert all(n.status == NodeStatus.COMPLETED for n in result.nodes)
    assert result.final_output is not None


def test_run_sync_raises_for_unknown_id() -> None:
    with pytest.raises(KeyError, match="Unknown execution_id"):
        run_sync("no-such-execution")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wait_for_execution(execution_id: str, timeout: float = 3.0) -> None:
    """Poll until the execution reaches a terminal state or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = get_status(execution_id)
        if status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
            return
        time.sleep(0.02)
    raise TimeoutError(f"Execution {execution_id} did not finish within {timeout}s")

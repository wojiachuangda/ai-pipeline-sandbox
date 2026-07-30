"""Workflow execution engine.

Provides trigger (async), synchronous execution, dry-run, status queries,
and a stub agent runner that does not depend on a real LLM.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from . import config
from .models import (
    DryRunResult,
    Execution,
    ExecutionStatus,
    NodeExecution,
    NodeStatus,
    Progress,
    WorkflowDef,
)
from .snapshot import SnapshotStore

# ---------------------------------------------------------------------------
# In-memory execution store (shared across the module)
# ---------------------------------------------------------------------------
_store: dict[str, Execution] = {}

# Default snapshot store – created lazily so tests can inject alternates.
_default_snapshot_store: SnapshotStore | None = None


def _get_snapshot_store() -> SnapshotStore:
    global _default_snapshot_store
    if _default_snapshot_store is None:
        _default_snapshot_store = SnapshotStore()
    return _default_snapshot_store


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def trigger(workflow_def: WorkflowDef) -> str:
    """Kick off an asynchronous workflow execution.

    Returns the ``execution_id`` immediately.  The execution runs in a
    background thread.

    AC-1: trigger returns execution_id immediately; async is default.
    """
    execution = _create_execution(workflow_def)
    _store[execution.id] = execution

    thread = threading.Thread(
        target=run_sync,
        args=(execution.id,),
        daemon=True,
    )
    thread.start()
    return execution.id


def run_sync(execution_id: str, *, snapshot_store: SnapshotStore | None = None) -> Execution:
    """Execute a workflow synchronously (blocks until completion or failure).

    Intended for use inside the background thread started by ``trigger()``
    and for deterministic testing.
    """
    execution = _store.get(execution_id)
    if execution is None:
        raise KeyError(f"Unknown execution_id: {execution_id}")

    snapshot = snapshot_store or _get_snapshot_store()

    execution.status = ExecutionStatus.RUNNING
    execution.updated_at = _timestamp()
    _store[execution.id] = execution

    try:
        for node_exec in execution.nodes:
            node_exec.status = NodeStatus.RUNNING
            node_exec.started_at = _timestamp()
            execution.updated_at = _timestamp()
            _store[execution.id] = execution
            snapshot.save(execution)

            try:
                node_exec.output = stub_agent_runner(node_exec.node_id)
                node_exec.status = NodeStatus.COMPLETED
            except Exception as exc:
                node_exec.status = NodeStatus.FAILED
                node_exec.error = str(exc)
                node_exec.finished_at = _timestamp()
                execution.updated_at = _timestamp()
                execution.status = ExecutionStatus.FAILED
                _store[execution.id] = execution
                snapshot.save(execution)
                return execution

            node_exec.finished_at = _timestamp()
            execution.updated_at = _timestamp()
            _store[execution.id] = execution
            snapshot.save(execution)

        # All nodes completed successfully — mark execution completed.
        execution.status = ExecutionStatus.COMPLETED
        execution.final_output = _build_final_output(execution)
        execution.updated_at = _timestamp()
        _store[execution.id] = execution
        snapshot.save(execution)
    except Exception:
        execution.status = ExecutionStatus.FAILED
        execution.updated_at = _timestamp()
        _store[execution.id] = execution
        snapshot.save(execution)
        raise

    return execution


def stub_agent_runner(node_id: str) -> dict[str, Any]:
    """Simulate an agent node execution without calling a real LLM.

    Returns a deterministic output stub based on *node_id* so tests can
    assert on per-node results.
    """
    # Artificially small delay so the "running" status is observable in tests.
    time.sleep(0.005)
    return {
        "node_id": node_id,
        "result": f"stub output for {node_id}",
        "model": "stub-agent/v0",
        "tokens": 0,
    }


def dry_run(workflow_def: WorkflowDef, mode: str = "FULL") -> DryRunResult:
    """Execute all nodes without persisting to the shared execution store.

    *mode* must be ``"FULL"`` — every node is executed via the stub runner
    and the returned ``DryRunResult`` carries the full trace plus
    ``final_output``.

    AC-3: dry_run FULL returns node_executions and final_output.
    """
    if mode != "FULL":
        raise ValueError(f"Unsupported dry_run mode: {mode!r} (expected 'FULL')")

    node_executions: list[NodeExecution] = []
    final_output: dict[str, Any] = {}

    for node_def in workflow_def.nodes:
        ne = NodeExecution(node_id=node_def.id)
        ne.status = NodeStatus.RUNNING
        ne.started_at = _timestamp()

        try:
            ne.output = stub_agent_runner(node_def.id)
            ne.status = NodeStatus.COMPLETED
        except Exception as exc:
            ne.status = NodeStatus.FAILED
            ne.error = str(exc)
            ne.finished_at = _timestamp()
            node_executions.append(ne)

            # On failure, collect what we have and stop.
            return DryRunResult(
                workflow_id=workflow_def.id,
                node_executions=node_executions,
                final_output=_dry_final_output(node_executions),
            )

        ne.finished_at = _timestamp()
        node_executions.append(ne)

    final_output = _dry_final_output(node_executions)
    return DryRunResult(
        workflow_id=workflow_def.id,
        node_executions=node_executions,
        final_output=final_output,
    )


def get_status(execution_id: str) -> ExecutionStatus | None:
    """Return the current status of an execution, or None if unknown.

    AC-4: status query returns progress and node status.
    """
    execution = _store.get(execution_id)
    if execution is None:
        return None
    return execution.status


def get_progress(execution_id: str) -> Progress | None:
    """Return a progress snapshot for an execution, or None if unknown.

    AC-4: progress includes completed/total counts and per-node status.
    """
    execution = _store.get(execution_id)
    if execution is None:
        return None
    completed = sum(
        1 for n in execution.nodes if n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED)
    )
    return Progress(
        execution_id=execution.id,
        status=execution.status,
        completed=completed,
        total=len(execution.nodes),
        nodes=list(execution.nodes),
    )


def get_concurrency_limit() -> int:
    """Return the currently configured concurrency limit.

    AC-6: concurrency limit is configurable and callers can read it.
    """
    return config.WORKFLOW_CONCURRENCY_LIMIT


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _create_execution(wf: WorkflowDef) -> Execution:
    now = _timestamp()
    nodes = [NodeExecution(node_id=nd.id) for nd in wf.nodes]
    return Execution(
        id=f"exec-{uuid.uuid4().hex[:12]}",
        workflow_id=wf.id,
        status=ExecutionStatus.PENDING,
        nodes=nodes,
        created_at=now,
        updated_at=now,
    )


def _build_final_output(execution: Execution) -> dict[str, Any]:
    """Aggregate outputs of all completed nodes into a single dict."""
    outputs: dict[str, Any] = {}
    for node in execution.nodes:
        if node.output is not None:
            outputs[node.node_id] = node.output
    return outputs


def _dry_final_output(node_executions: list[NodeExecution]) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    for ne in node_executions:
        if ne.output is not None:
            outputs[ne.node_id] = ne.output
    return outputs


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()

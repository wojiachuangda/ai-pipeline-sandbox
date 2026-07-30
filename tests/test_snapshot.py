"""Tests for the snapshot persistence layer.

Covers AC-5: save/load round-trip and crash-recovery simulation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from sandbox_app.models import (
    Execution,
    ExecutionStatus,
    NodeExecution,
    NodeStatus,
)
from sandbox_app.snapshot import SnapshotStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_execution(
    eid: str = "exec-test-1",
    wf_id: str = "wf-test",
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
) -> Execution:
    """Build a completed execution with two nodes for testing."""
    nodes = [
        NodeExecution(
            node_id="node-1",
            status=NodeStatus.COMPLETED,
            output={"result": "ok-node-1"},
            started_at="2026-07-30T10:00:00+00:00",
            finished_at="2026-07-30T10:00:01+00:00",
        ),
        NodeExecution(
            node_id="node-2",
            status=NodeStatus.COMPLETED,
            output={"result": "ok-node-2"},
            started_at="2026-07-30T10:00:02+00:00",
            finished_at="2026-07-30T10:00:03+00:00",
        ),
    ]
    return Execution(
        id=eid,
        workflow_id=wf_id,
        status=status,
        nodes=nodes,
        created_at="2026-07-30T09:59:59+00:00",
        updated_at="2026-07-30T10:00:03+00:00",
        final_output={"node-1": {"result": "ok-node-1"}, "node-2": {"result": "ok-node-2"}},
    )


# ---------------------------------------------------------------------------
# AC-5: snapshot save / load
# ---------------------------------------------------------------------------


def test_snapshot_save_and_load() -> None:
    """save() + load() round-trip restores full Execution object."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SnapshotStore(base_dir=tmp)
        execution = _make_execution()

        path = store.save(execution)
        assert Path(path).exists()

        loaded = store.load(execution.id)
        assert loaded is not None

        # Verify top-level fields.
        assert loaded.id == execution.id
        assert loaded.workflow_id == execution.workflow_id
        assert loaded.status == execution.status
        assert loaded.final_output == execution.final_output

        # Verify nodes.
        assert len(loaded.nodes) == len(execution.nodes)
        for orig, restored in zip(execution.nodes, loaded.nodes):
            assert restored.node_id == orig.node_id
            assert restored.status == orig.status
            assert restored.output == orig.output
            assert restored.error == orig.error
            assert restored.started_at == orig.started_at
            assert restored.finished_at == orig.finished_at


def test_snapshot_load_missing_returns_none() -> None:
    """load() returns None for an execution_id that was never saved."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SnapshotStore(base_dir=tmp)
        assert store.load("no-such-id") is None


def test_snapshot_delete() -> None:
    """delete() removes the snapshot file; subsequent load returns None."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SnapshotStore(base_dir=tmp)
        execution = _make_execution(eid="exec-del")
        store.save(execution)
        assert store.load("exec-del") is not None

        removed = store.delete("exec-del")
        assert removed is True
        assert store.load("exec-del") is None


def test_snapshot_delete_missing_returns_false() -> None:
    """delete() returns False when the snapshot does not exist."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SnapshotStore(base_dir=tmp)
        assert store.delete("never-saved") is False


# ---------------------------------------------------------------------------
# AC-5: crash recovery simulation
# ---------------------------------------------------------------------------


def test_snapshot_crash_recovery() -> None:
    """Simulate an interrupted execution — snapshot contains partial progress.

    Workflow: two nodes.  Node-1 completed; node-2 still pending (crashed
    before it started).  From the snapshot we can see which node completed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = SnapshotStore(base_dir=tmp)

        # Simulate a mid-execution save (node-1 done, node-2 pending).
        crashed = Execution(
            id="exec-crash",
            workflow_id="wf-crash",
            status=ExecutionStatus.RUNNING,
            nodes=[
                NodeExecution(
                    node_id="node-1",
                    status=NodeStatus.COMPLETED,
                    output={"result": "done"},
                    started_at="2026-07-30T10:00:00+00:00",
                    finished_at="2026-07-30T10:00:01+00:00",
                ),
                NodeExecution(
                    node_id="node-2",
                    status=NodeStatus.PENDING,
                ),
            ],
            created_at="2026-07-30T09:59:59+00:00",
            updated_at="2026-07-30T10:00:01+00:00",
        )
        store.save(crashed)

        # "Recover" — load the snapshot.
        recovered = store.load("exec-crash")
        assert recovered is not None
        assert recovered.status == ExecutionStatus.RUNNING
        assert len(recovered.nodes) == 2

        # Node-1 was complete before the crash.
        n1 = next(n for n in recovered.nodes if n.node_id == "node-1")
        assert n1.status == NodeStatus.COMPLETED
        assert n1.output == {"result": "done"}

        # Node-2 never ran — still pending.
        n2 = next(n for n in recovered.nodes if n.node_id == "node-2")
        assert n2.status == NodeStatus.PENDING
        assert n2.output is None


def test_snapshot_overwrite() -> None:
    """Saving the same execution_id twice overwrites the previous snapshot."""
    with tempfile.TemporaryDirectory() as tmp:
        store = SnapshotStore(base_dir=tmp)

        v1 = _make_execution(eid="exec-overwrite")
        v1.status = ExecutionStatus.RUNNING
        store.save(v1)

        v2 = _make_execution(eid="exec-overwrite")
        v2.status = ExecutionStatus.COMPLETED
        store.save(v2)

        loaded = store.load("exec-overwrite")
        assert loaded is not None
        assert loaded.status == ExecutionStatus.COMPLETED

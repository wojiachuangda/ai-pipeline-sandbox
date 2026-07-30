"""Snapshot persistence layer for workflow executions.

Stores execution state as JSON files so progress can be recovered after a crash.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .config import WORKFLOW_SNAPSHOT_DIR
from .models import Execution, ExecutionStatus, NodeExecution, NodeStatus


class SnapshotStore:
    """File-backed snapshot store for Execution objects.

    Each execution is persisted as a single JSON file inside a directory tree.
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        """Create a store.

        *base_dir* overrides the configured WORKFLOW_SNAPSHOT_DIR and the
        default temp-directory fallback.  If *base_dir* does not exist it is
        created on the first ``save()`` call.
        """
        if base_dir is not None:
            self._base = Path(base_dir)
        elif WORKFLOW_SNAPSHOT_DIR is not None:
            self._base = Path(WORKFLOW_SNAPSHOT_DIR)
        else:
            self._base = Path(tempfile.gettempdir()) / "workflow_snapshots"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, execution: Execution) -> Path:
        """Persist *execution* to disk and return the file path."""
        self._base.mkdir(parents=True, exist_ok=True)
        path = self._snapshot_path(execution.id)
        payload = _execution_to_dict(execution)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return path

    def load(self, execution_id: str) -> Execution | None:
        """Load an execution from its snapshot, or None if not found."""
        path = self._snapshot_path(execution_id)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        return _execution_from_dict(payload)

    def delete(self, execution_id: str) -> bool:
        """Remove the snapshot file.  Returns True if a file was deleted."""
        path = self._snapshot_path(execution_id)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _snapshot_path(self, execution_id: str) -> Path:
        return self._base / f"{execution_id}.json"


# ======================================================================
# Serialisation helpers (private)
# ======================================================================


def _execution_to_dict(ex: Execution) -> dict[str, Any]:
    return {
        "id": ex.id,
        "workflow_id": ex.workflow_id,
        "status": ex.status.value,
        "nodes": [_node_execution_to_dict(n) for n in ex.nodes],
        "created_at": ex.created_at,
        "updated_at": ex.updated_at,
        "final_output": ex.final_output,
    }


def _execution_from_dict(d: dict[str, Any]) -> Execution:
    return Execution(
        id=d["id"],
        workflow_id=d["workflow_id"],
        status=ExecutionStatus(d["status"]),
        nodes=[_node_execution_from_dict(n) for n in d.get("nodes", [])],
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
        final_output=d.get("final_output"),
    )


def _node_execution_to_dict(ne: NodeExecution) -> dict[str, Any]:
    return {
        "node_id": ne.node_id,
        "status": ne.status.value,
        "output": ne.output,
        "error": ne.error,
        "started_at": ne.started_at,
        "finished_at": ne.finished_at,
    }


def _node_execution_from_dict(d: dict[str, Any]) -> NodeExecution:
    return NodeExecution(
        node_id=d["node_id"],
        status=NodeStatus(d["status"]),
        output=d.get("output"),
        error=d.get("error"),
        started_at=d.get("started_at"),
        finished_at=d.get("finished_at"),
    )

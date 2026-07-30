"""Execution data model and in-memory result store.

Defines status / dead-letter-action enums, the ``ExecutionResult``
dataclass, and a thread-unsafe ``ExecutionStore`` backed by a plain dict.
"""

from __future__ import annotations

__all__ = [
    "DeadLetterAction",
    "ExecutionResult",
    "ExecutionStatus",
    "ExecutionStore",
]

import time
from dataclasses import dataclass, field
from enum import Enum, auto

from sandbox_app.trace import build_logs_url, generate_execution_id, generate_trace_id


class ExecutionStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    DEAD_LETTER = auto()


class DeadLetterAction(Enum):
    REQUEUE = "requeue"
    DISCARD = "discard"
    MANUAL_FIX = "manual_fix"


@dataclass
class ExecutionResult:
    """Full snapshot of a single execution attempt.

    Attributes:
        input_snapshot: Positional/keyword args captured at call time.
        max_output_chars: Threshold at which *output* is truncated on save.
            (Stored on the result so ``ExecutionStore`` can honour it
            without a separate config parameter.)
    """

    execution_id: str = field(default_factory=generate_execution_id)
    trace_id: str = field(default_factory=generate_trace_id)
    status: ExecutionStatus = ExecutionStatus.PENDING
    input_snapshot: dict = field(default_factory=dict)
    output: str | None = None
    error: str | None = None
    duration_ms: float | None = None
    logs_url: str | None = None
    created_at: float = field(default_factory=time.time)
    retry_count: int = 0

    # ------------------------------------------------------------------
    # Truncation threshold – honoured by ExecutionStore.save()
    # ------------------------------------------------------------------
    max_output_chars: int = 10_000  # 10 KiB default


class ExecutionStore:
    """In-memory store of :class:`ExecutionResult` records.

    .. note::

        This store is purposely **not** thread-safe.  For concurrent use
        guard access with an external lock.
    """

    def __init__(self) -> None:
        self._records: dict[str, ExecutionResult] = {}

    # ------------------------------------------------------------------
    def save(self, result: ExecutionResult) -> None:
        """Persist *result*, truncating its output if needed."""
        if result.output is not None and len(result.output) > result.max_output_chars:
            overflow = len(result.output) - result.max_output_chars
            result.output = result.output[: result.max_output_chars] + (
                f"…[truncated {overflow} chars]"
            )
        if result.logs_url is None:
            result.logs_url = build_logs_url(result.execution_id)
        self._records[result.execution_id] = result

    # ------------------------------------------------------------------
    def get(self, execution_id: str) -> ExecutionResult | None:
        """Return the stored result or ``None``."""
        return self._records.get(execution_id)

    # ------------------------------------------------------------------
    def list_by_status(self, status: ExecutionStatus) -> list[ExecutionResult]:
        """Return every stored result whose *status* matches."""
        return [r for r in self._records.values() if r.status is status]

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._records)

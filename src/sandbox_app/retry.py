"""Retry logic with configurable back-off and dead-letter handling.

Exposes:

* ``RetryConfig`` – controls max_retries, base delay, and multiplier.
* ``DeadLetterQueue`` – collects results whose retries are exhausted.
* ``ExecutionContext`` – orchestrates a callable through the retry /
  dead-letter lifecycle and persists every result to an ``ExecutionStore``.
"""

from __future__ import annotations

__all__ = [
    "DeadLetterEntry",
    "DeadLetterQueue",
    "ExecutionContext",
    "RetryConfig",
]

import time
import traceback
from dataclasses import dataclass, field

from sandbox_app.execution import (
    ExecutionResult,
    ExecutionStatus,
    ExecutionStore,
)
from sandbox_app.trace import build_logs_url, generate_execution_id, generate_trace_id


# ---------------------------------------------------------------------------
# RetryConfig
# ---------------------------------------------------------------------------


@dataclass
class RetryConfig:
    """Tunable exponential-backoff retry behaviour.

    The *n*-th retry (1-indexed) sleeps for::

        min(base_delay_seconds * backoff_multiplier ^ (attempt - 1),
            max_delay_seconds)
    """

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 60.0


# ---------------------------------------------------------------------------
# DeadLetterEntry
# ---------------------------------------------------------------------------


@dataclass
class DeadLetterEntry:
    """A single dead-lettered execution."""

    execution_result: ExecutionResult
    failure_count: int
    last_error: str
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# DeadLetterQueue
# ---------------------------------------------------------------------------


class DeadLetterQueue:
    """In-memory dead-letter queue.

    Accepts :class:`DeadLetterEntry` instances pushed when retries are
    exhausted.  Supports three operations:

    * ``requeue`` – remove and return the entry so the caller can re-
      execute.
    * ``discard`` – permanently drop the entry.
    * ``mark_manual_fix`` – record the entry as needing human
      intervention (the entry stays in the queue until explicitly
      discarded).
    """

    def __init__(self) -> None:
        self._entries: list[DeadLetterEntry] = []
        self._manual_fix: set[str] = set()

    # -- mutation -----------------------------------------------------------

    def push(self, entry: DeadLetterEntry) -> None:
        """Add *entry* to the dead-letter queue."""
        self._entries.append(entry)

    def requeue(self, execution_id: str) -> DeadLetterEntry | None:
        """Pop and return the entry identified by *execution_id*."""
        for i, entry in enumerate(self._entries):
            if entry.execution_result.execution_id == execution_id:
                del self._entries[i]
                self._manual_fix.discard(execution_id)
                return entry
        return None

    def discard(self, execution_id: str) -> bool:
        """Remove the entry.  Returns ``True`` if it existed."""
        for i, entry in enumerate(self._entries):
            if entry.execution_result.execution_id == execution_id:
                del self._entries[i]
                self._manual_fix.discard(execution_id)
                return True
        return False

    def mark_manual_fix(self, execution_id: str) -> bool:
        """Tag an entry that requires human intervention.

        Returns ``True`` if the entry exists in the queue; ``False``
        otherwise.
        """
        for entry in self._entries:
            if entry.execution_result.execution_id == execution_id:
                self._manual_fix.add(execution_id)
                return True
        return False

    # -- query --------------------------------------------------------------

    def list_all(self) -> list[DeadLetterEntry]:
        """Return every entry currently in the queue."""
        return list(self._entries)

    def get(self, execution_id: str) -> DeadLetterEntry | None:
        """Look up one entry by execution id."""
        for entry in self._entries:
            if entry.execution_result.execution_id == execution_id:
                return entry
        return None

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# ExecutionContext
# ---------------------------------------------------------------------------


class ExecutionContext:
    """Wraps a callable with retry + dead-letter logic.

    Typical usage::

        ctx = ExecutionContext(RetryConfig(max_retries=3))
        result = ctx.execute(my_task, "arg", kw=42)
    """

    def __init__(
        self,
        retry_config: RetryConfig | None = None,
        store: ExecutionStore | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
    ) -> None:
        self.retry_config = retry_config if retry_config is not None else RetryConfig()
        self.store = store if store is not None else ExecutionStore()
        self.dead_letter_queue = (
            dead_letter_queue if dead_letter_queue is not None else DeadLetterQueue()
        )

    # ------------------------------------------------------------------
    def execute(self, fn, *args, **kwargs) -> ExecutionResult:
        """Invoke *fn* with retry, saving every attempt to the store.

        On terminal failure the result is pushed into
        :attr:`dead_letter_queue` and its status is set to
        ``DEAD_LETTER``.
        """
        execution_id = generate_execution_id()
        trace_id = generate_trace_id()
        logs_url = build_logs_url(execution_id)
        started_at = time.time()

        last_error: str | None = None
        cfg = self.retry_config

        for attempt in range(cfg.max_retries + 1):
            result = ExecutionResult(
                execution_id=execution_id,
                trace_id=trace_id,
                status=ExecutionStatus.RUNNING,
                input_snapshot={"args": args, "kwargs": kwargs},
                logs_url=logs_url,
                retry_count=attempt,
            )
            self.store.save(result)

            try:
                output = fn(*args, **kwargs)
            except Exception:
                last_error = traceback.format_exc()
                if attempt < cfg.max_retries:
                    delay = min(
                        cfg.base_delay_seconds
                        * (cfg.backoff_multiplier ** attempt),
                        cfg.max_delay_seconds,
                    )
                    time.sleep(delay)
                    continue
                # Retries exhausted → dead letter
                result.status = ExecutionStatus.DEAD_LETTER
                result.error = last_error
                result.duration_ms = (time.time() - started_at) * 1000
                self.store.save(result)
                self.dead_letter_queue.push(
                    DeadLetterEntry(
                        execution_result=result,
                        failure_count=attempt + 1,
                        last_error=last_error,
                    )
                )
                return result

            # Success path
            result.status = ExecutionStatus.SUCCEEDED
            result.output = str(output)
            result.duration_ms = (time.time() - started_at) * 1000
            self.store.save(result)
            return result

        # Should be unreachable – kept for type-safety
        result = ExecutionResult(
            execution_id=execution_id,
            trace_id=trace_id,
            status=ExecutionStatus.DEAD_LETTER,
            input_snapshot={"args": args, "kwargs": kwargs},
            error=last_error or "unknown error",
            duration_ms=(time.time() - started_at) * 1000,
            logs_url=logs_url,
            retry_count=cfg.max_retries,
        )
        self.store.save(result)
        self.dead_letter_queue.push(
            DeadLetterEntry(
                execution_result=result,
                failure_count=cfg.max_retries + 1,
                last_error=last_error or "unknown error",
            )
        )
        return result

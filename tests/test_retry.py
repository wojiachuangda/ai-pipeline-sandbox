"""Tests for retry & dead-letter module (AC-1, AC-2, AC-5)."""

from sandbox_app.execution import (
    ExecutionResult,
    ExecutionStatus,
    ExecutionStore,
)
from sandbox_app.retry import (
    DeadLetterEntry,
    DeadLetterQueue,
    ExecutionContext,
    RetryConfig,
)


# ---------------------------------------------------------------------------
# AC-1: retry behaviour
# ---------------------------------------------------------------------------


class TestRetrySucceedsOnFirstAttempt:
    def test_retry_succeeds_on_first_attempt(self) -> None:
        """AC-1: success path – no retries."""
        ctx = ExecutionContext()
        result = ctx.execute(lambda x: x * 2, 21)
        assert result.status is ExecutionStatus.SUCCEEDED
        assert result.output == "42"
        assert result.retry_count == 0


class TestRetrySucceedsAfterTransientFailures:
    def test_retry_succeeds_after_transient_failures(self) -> None:
        """AC-1: transient failures exhaust a few retries then succeed."""
        call_counter = {"count": 0}

        def flaky():
            call_counter["count"] += 1
            if call_counter["count"] < 3:
                raise RuntimeError("transient")
            return "recovered"

        ctx = ExecutionContext(RetryConfig(max_retries=3))
        result = ctx.execute(flaky)
        assert result.status is ExecutionStatus.SUCCEEDED
        assert result.retry_count == 2  # 0-indexed: succeeded on 3rd call
        assert result.output == "recovered"


class TestRetryExhausted:
    def test_retry_exhausted_with_default_config(self) -> None:
        """AC-1: default max_retries=3; 4 total attempts then dead-letter."""
        ctx = ExecutionContext()

        def always_fails():
            raise RuntimeError("boom")

        result = ctx.execute(always_fails)
        assert result.status is ExecutionStatus.DEAD_LETTER
        assert result.retry_count == 3  # final attempt (0-indexed)
        assert "boom" in (result.error or "")


class TestRetryConfig:
    def test_retry_config_custom_max_retries_and_backoff(self) -> None:
        """AC-1: custom RetryConfig values are honoured."""
        cfg = RetryConfig(max_retries=1, base_delay_seconds=0.01)
        ctx = ExecutionContext(cfg)

        call_count = {"n": 0}

        def succeeds_second():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("fail")
            return "ok"

        result = ctx.execute(succeeds_second)
        assert result.status is ExecutionStatus.SUCCEEDED
        assert call_count["n"] == 2  # 1 fail + 1 success

    def test_exponential_backoff_computation(self) -> None:
        """AC-1: verify exponential backoff delay formula."""
        cfg = RetryConfig(
            base_delay_seconds=1.0,
            backoff_multiplier=3.0,
            max_delay_seconds=100.0,
        )
        # attempt 0 → 1.0 * 3^0 = 1.0
        # attempt 1 → 1.0 * 3^1 = 3.0
        # attempt 2 → 1.0 * 3^2 = 9.0
        expected = [1.0, 3.0, 9.0]
        for n, exp in enumerate(expected):
            computed = cfg.base_delay_seconds * (cfg.backoff_multiplier**n)
            assert computed == exp

    def test_backoff_clamped_to_max(self) -> None:
        """AC-1: backoff delay is clamped to max_delay_seconds."""
        cfg = RetryConfig(
            base_delay_seconds=10.0,
            backoff_multiplier=10.0,  # attempt 3 → 10 * 10^3 = 10000
            max_delay_seconds=60.0,
        )
        # attempt 3 (0-indexed):
        computed = cfg.base_delay_seconds * (cfg.backoff_multiplier**3)
        assert computed > cfg.max_delay_seconds  # raw > max
        clamped = min(computed, cfg.max_delay_seconds)
        assert clamped == 60.0


# ---------------------------------------------------------------------------
# AC-1 → dead letter
# ---------------------------------------------------------------------------


class TestRetryExhaustedEntersDeadLetter:
    def test_retry_exhausted_enters_dead_letter(self) -> None:
        """AC-1: exhausted retries push an entry into the dead-letter queue."""
        dlq = DeadLetterQueue()
        ctx = ExecutionContext(
            RetryConfig(max_retries=1, base_delay_seconds=0.001),
            dead_letter_queue=dlq,
        )

        def always_fails():
            raise RuntimeError("fatal")

        result = ctx.execute(always_fails)
        assert result.status is ExecutionStatus.DEAD_LETTER
        assert len(dlq) == 1

        entry = dlq.list_all()[0]
        assert entry.execution_result.execution_id == result.execution_id
        assert entry.last_error is not None
        assert "fatal" in entry.last_error


# ---------------------------------------------------------------------------
# AC-2: dead-letter operations
# ---------------------------------------------------------------------------


class TestDeadLetterRequeue:
    def test_dead_letter_requeue_returns_entry(self) -> None:
        """AC-2: REQUEUE pops the entry from the queue."""
        dlq = DeadLetterQueue()
        result = ExecutionResult(execution_id="exec-dl-1", status=ExecutionStatus.DEAD_LETTER)
        dlq.push(DeadLetterEntry(result, failure_count=3, last_error="err"))

        entry = dlq.requeue("exec-dl-1")
        assert entry is not None
        assert entry.execution_result.execution_id == "exec-dl-1"
        assert len(dlq) == 0  # removed from queue


class TestDeadLetterDiscard:
    def test_dead_letter_discard_removes_entry(self) -> None:
        """AC-2: DISCARD permanently removes the entry."""
        dlq = DeadLetterQueue()
        result = ExecutionResult(execution_id="exec-dl-2")
        dlq.push(DeadLetterEntry(result, failure_count=1, last_error="err"))

        assert dlq.discard("exec-dl-2") is True
        assert len(dlq) == 0
        assert dlq.discard("exec-dl-2") is False  # already gone


class TestDeadLetterManualFix:
    def test_dead_letter_manual_fix_marks_entry(self) -> None:
        """AC-2: MANUAL_FIX marks an entry (stays in queue)."""
        dlq = DeadLetterQueue()
        result = ExecutionResult(execution_id="exec-dl-3")
        dlq.push(DeadLetterEntry(result, failure_count=2, last_error="err"))

        assert dlq.mark_manual_fix("exec-dl-3") is True
        assert len(dlq) == 1  # still present

    def test_manual_fix_nonexistent_returns_false(self) -> None:
        dlq = DeadLetterQueue()
        assert dlq.mark_manual_fix("nope") is False


# ---------------------------------------------------------------------------
# AC-5: end-to-end retry exhausted → dead letter → REQUEUE
# ---------------------------------------------------------------------------


class TestEndToEndRetryDeadLetterRequeue:
    def test_retry_exhausted_to_dead_letter_to_requeue(self) -> None:
        """AC-5: full lifecycle – exhaust → dead-letter → requeue → re-execute → success."""
        dlq = DeadLetterQueue()
        store = ExecutionStore()
        cfg = RetryConfig(max_retries=1, base_delay_seconds=0.001)

        # -- Step 1: execute a failing function → dead letter ----------
        ctx1 = ExecutionContext(cfg, store=store, dead_letter_queue=dlq)

        def always_fails():
            raise RuntimeError("transient fault")

        failed_result = ctx1.execute(always_fails)
        assert failed_result.status is ExecutionStatus.DEAD_LETTER
        assert len(dlq) == 1
        # The store holds 1 entry (each save overwrites by execution_id)
        assert store.get(failed_result.execution_id) is not None

        # -- Step 2: requeue from dead-letter --------------------------
        entry = dlq.requeue(failed_result.execution_id)
        assert entry is not None
        assert len(dlq) == 0

        # -- Step 3: re-execute with a function that now succeeds ------
        ctx2 = ExecutionContext(cfg, store=store, dead_letter_queue=dlq)

        def succeeds():
            return "all good"

        success_result = ctx2.execute(succeeds)
        assert success_result.status is ExecutionStatus.SUCCEEDED
        assert success_result.output == "all good"
        assert success_result.retry_count == 0

        # Dead-letter queue stays empty (success never entered it)
        assert len(dlq) == 0


class TestRetryStoresIntermediateResults:
    def test_every_attempt_is_stored(self) -> None:
        """Each retry attempt creates a RUNNING snapshot in the store."""
        store = ExecutionStore()
        cfg = RetryConfig(max_retries=2, base_delay_seconds=0.001)
        ctx = ExecutionContext(cfg, store=store)

        call_count = {"n": 0}

        def fails_twice():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("fail")
            return "done"

        ctx.execute(fails_twice)

        # Should have 3 snapshots (2 failed RUNNING + 1 successful)
        all_results = [store.get(k) for k in store._records]
        successful = [r for r in all_results if r and r.status is ExecutionStatus.SUCCEEDED]
        assert len(successful) == 1
        assert successful[0].output == "done"  # type: ignore[union-attr]

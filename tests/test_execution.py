"""Tests for execution module (AC-3: result fields, store, truncation)."""

from sandbox_app.execution import (
    ExecutionResult,
    ExecutionStatus,
    ExecutionStore,
)


class TestExecutionResult:
    def test_execution_result_contains_all_fields(self) -> None:
        """AC-3: input_snapshot / output / status / duration are present."""
        result = ExecutionResult(
            execution_id="exec-001",
            trace_id="trace-001",
            status=ExecutionStatus.SUCCEEDED,
            input_snapshot={"args": (1, 2), "kwargs": {"mode": "test"}},
            output="hello world",
            duration_ms=123.45,
            retry_count=0,
        )
        assert result.execution_id == "exec-001"
        assert result.trace_id == "trace-001"
        assert result.status is ExecutionStatus.SUCCEEDED
        assert result.input_snapshot == {"args": (1, 2), "kwargs": {"mode": "test"}}
        assert result.output == "hello world"
        assert result.duration_ms == 123.45
        assert result.retry_count == 0
        assert result.created_at > 0

    def test_default_status_is_pending(self) -> None:
        result = ExecutionResult()
        assert result.status is ExecutionStatus.PENDING


class TestExecutionStore:
    def test_save_and_retrieve(self) -> None:
        """AC-3: store can persist and retrieve a result."""
        store = ExecutionStore()
        result = ExecutionResult(execution_id="e1")
        store.save(result)
        retrieved = store.get("e1")
        assert retrieved is not None
        assert retrieved.execution_id == "e1"

    def test_get_missing_returns_none(self) -> None:
        store = ExecutionStore()
        assert store.get("nonexistent") is None

    def test_list_by_status(self) -> None:
        """AC-3: filter stored results by status."""
        store = ExecutionStore()
        r1 = ExecutionResult(
            execution_id="e1", status=ExecutionStatus.SUCCEEDED, output="ok"
        )
        r2 = ExecutionResult(
            execution_id="e2", status=ExecutionStatus.FAILED, error="boom"
        )
        r3 = ExecutionResult(
            execution_id="e3", status=ExecutionStatus.FAILED, error="also boom"
        )
        for r in (r1, r2, r3):
            store.save(r)

        succeeded = store.list_by_status(ExecutionStatus.SUCCEEDED)
        failed = store.list_by_status(ExecutionStatus.FAILED)

        assert len(succeeded) == 1
        assert succeeded[0].execution_id == "e1"
        assert len(failed) == 2
        assert {r.execution_id for r in failed} == {"e2", "e3"}

    def test_len(self) -> None:
        store = ExecutionStore()
        assert len(store) == 0
        store.save(ExecutionResult(execution_id="e1"))
        assert len(store) == 1


class TestLargeOutputTruncation:
    def test_small_output_not_truncated(self) -> None:
        store = ExecutionStore()
        result = ExecutionResult(
            execution_id="e1", output="short", max_output_chars=100
        )
        store.save(result)
        assert store.get("e1").output == "short"  # type: ignore[union-attr]

    def test_large_output_is_truncated(self) -> None:
        """AC-3: output exceeding max_output_chars is truncated with marker."""
        store = ExecutionStore()
        result = ExecutionResult(
            execution_id="e1",
            output="x" * 200,
            max_output_chars=100,
        )
        store.save(result)
        saved = store.get("e1")
        assert saved is not None
        assert saved.output is not None
        assert saved.output.startswith("x" * 100)
        assert "truncated" in saved.output
        assert "100 chars" in saved.output  # 200 - 100 = 100

    def test_truncation_with_custom_threshold(self) -> None:
        store = ExecutionStore()
        result = ExecutionResult(
            execution_id="e1",
            output="a" * 50,
            max_output_chars=10,
        )
        store.save(result)
        saved = store.get("e1")
        assert saved is not None
        assert saved.output is not None
        assert "truncated 40 chars" in saved.output

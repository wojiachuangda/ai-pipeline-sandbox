"""Tests for trace module (AC-4: execution_id ↔ trace_id, logs_url)."""

from sandbox_app import build_logs_url, generate_execution_id, generate_trace_id
from sandbox_app.trace import TraceInfo


class TestTraceIdFormat:
    def test_trace_id_format(self) -> None:
        """AC-4: trace_id follows the expected pattern."""
        tid = generate_trace_id()
        assert tid.startswith("trace-")
        assert len(tid) == len("trace-") + 12  # 12 hex chars

    def test_execution_id_format(self) -> None:
        """AC-4: execution_id follows the expected pattern."""
        eid = generate_execution_id()
        assert eid.startswith("exec-")
        assert len(eid) == len("exec-") + 12


class TestTraceIdUniqueness:
    def test_generated_ids_are_unique(self) -> None:
        ids = {generate_trace_id() for _ in range(100)}
        assert len(ids) == 100


class TestBuildLogsUrl:
    def test_logs_url_contains_execution_id(self) -> None:
        url = build_logs_url("exec-abc123")
        assert "exec-abc123" in url
        assert url.startswith("/logs/")
        assert url.endswith(".log")


class TestTraceInfo:
    def test_default_ids_are_populated(self) -> None:
        info = TraceInfo()
        assert info.trace_id.startswith("trace-")
        assert info.execution_id.startswith("exec-")

    def test_execution_result_links_trace_id(self) -> None:
        """AC-4: execution_id and trace_id are both present and distinct."""
        from sandbox_app.execution import ExecutionResult

        result = ExecutionResult()
        assert result.execution_id.startswith("exec-")
        assert result.trace_id.startswith("trace-")
        assert result.execution_id != result.trace_id

    def test_logs_url_in_result(self) -> None:
        """AC-4: logs_url is populated on the result by the store."""
        from sandbox_app.execution import ExecutionResult, ExecutionStore

        result = ExecutionResult(execution_id="exec-test123")
        store = ExecutionStore()
        store.save(result)
        retrieved = store.get("exec-test123")
        assert retrieved is not None
        assert retrieved.logs_url == "/logs/exec-test123.log"

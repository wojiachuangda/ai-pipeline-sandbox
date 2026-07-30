"""Tests for sandbox_app.logging — AC-1 (structured logs) + AC-2 (trace/span)."""

import time

import pytest

from sandbox_app.logging import (
    clear_logs,
    clear_traces,
    get_spans,
    get_trace_tree,
    put_span,
    query_logs,
    write_log,
)


@pytest.fixture(autouse=True)
def _clean() -> None:
    clear_logs()
    clear_traces()


# ---------------------------------------------------------------------------
# AC-1: Structured logging
# ---------------------------------------------------------------------------


class TestWriteAndQueryLogs:
    def test_write_and_retrieve(self) -> None:
        """AC-1.1: write one log entry and query it back."""
        t0 = time.time()
        write_log("INFO", "hello", agent_id="agent-1")
        results = query_logs(t0 - 1, t0 + 1)
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["message"] == "hello"
        assert results[0]["agent_id"] == "agent-1"

    def test_filter_by_level(self) -> None:
        """AC-1.2: filter by level."""
        t0 = time.time()
        write_log("INFO", "info msg", timestamp=t0)
        write_log("ERROR", "error msg", timestamp=t0)
        results = query_logs(t0 - 1, t0 + 1, level="ERROR")
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["level"] == "ERROR"

    def test_filter_by_agent_id(self) -> None:
        """AC-1.3: filter by agent_id."""
        t0 = time.time()
        write_log("INFO", "a1", agent_id="agent-1", timestamp=t0)
        write_log("INFO", "a2", agent_id="agent-2", timestamp=t0)
        results = query_logs(t0 - 1, t0 + 1, agent_id="agent-1")
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["message"] == "a1"

    def test_time_range_exceeded(self) -> None:
        """AC-1.4: > 24h window returns LOG_TIME_RANGE_EXCEEDED."""
        t0 = time.time()
        result = query_logs(t0, t0 + 25 * 3600)
        assert isinstance(result, dict)
        assert result["error"] == "LOG_TIME_RANGE_EXCEEDED"
        assert result["max_hours"] == 24

    def test_empty_result(self) -> None:
        """AC-1.5: no matching logs → empty list."""
        t0 = time.time()
        write_log("INFO", "msg", timestamp=t0)
        results = query_logs(t0 + 100, t0 + 200)
        assert isinstance(results, list)
        assert results == []

    def test_time_window_boundaries(self) -> None:
        """Logs exactly at boundary are included."""
        t0 = time.time()
        write_log("INFO", "boundary", timestamp=t0 + 10)
        results = query_logs(t0, t0 + 10)
        assert isinstance(results, list)
        assert len(results) == 1

    def test_exactly_24h_window(self) -> None:
        """24h window is allowed (slightly under limit)."""
        t0 = time.time()
        # 23:59:59 is within limit
        results = query_logs(t0, t0 + 23.999 * 3600)
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# AC-2: Trace / Span
# ---------------------------------------------------------------------------


class TestSpanQuery:
    def test_trace_not_found(self) -> None:
        """AC-2.1: querying a nonexistent trace returns NOT_FOUND."""
        result = get_spans("nonexistent")
        assert isinstance(result, dict)
        assert result["error"] == "NOT_FOUND"

    def test_get_spans_for_trace(self) -> None:
        """AC-2.2: store 3 spans and retrieve them all."""
        put_span("trace-1", "span-1", "op-1")
        put_span("trace-1", "span-2", "op-2")
        put_span("trace-1", "span-3", "op-3")
        spans = get_spans("trace-1")
        assert isinstance(spans, list)
        assert len(spans) == 3

    def test_trace_tree_structure(self) -> None:
        """AC-2.3: trace_tree returns correct nested structure."""
        put_span("trace-2", "root", "parent-op", parent_span_id=None)
        put_span("trace-2", "child-1", "child-op-1", parent_span_id="root")
        put_span("trace-2", "child-2", "child-op-2", parent_span_id="root")
        put_span("trace-2", "grandchild", "gc-op", parent_span_id="child-1")

        tree = get_trace_tree("trace-2")
        assert isinstance(tree, dict)
        assert "error" not in tree
        assert tree["trace_id"] == "trace-2"

        root = tree["root"]
        assert root is not None
        assert root["span"]["span_id"] == "root"
        assert len(root["children"]) == 2

        child_ids = {c["span"]["span_id"] for c in root["children"]}
        assert child_ids == {"child-1", "child-2"}

        # Find child-1 and check its child
        for c in root["children"]:
            if c["span"]["span_id"] == "child-1":
                assert len(c["children"]) == 1
                assert c["children"][0]["span"]["span_id"] == "grandchild"

    def test_empty_trace_not_found_tree(self) -> None:
        """AC-2.4: empty trace returns NOT_FOUND for tree too."""
        result = get_trace_tree("empty-trace")
        assert isinstance(result, dict)
        assert result["error"] == "NOT_FOUND"

    def test_trace_not_found_spans(self) -> None:
        """AC-2.1 variant: nonexistent trace via get_spans."""
        result = get_spans("no-such-trace")
        assert isinstance(result, dict)
        assert result["error"] == "NOT_FOUND"

    def test_single_span_trace_tree(self) -> None:
        """A single-span trace forms a tree with one node, no children."""
        put_span("trace-solo", "solo", "lone-op")
        tree = get_trace_tree("trace-solo")
        assert isinstance(tree, dict)
        assert "error" not in tree
        assert tree["root"] is not None
        assert tree["root"]["span"]["span_id"] == "solo"
        assert tree["root"]["children"] == []

    def test_spans_isolated_by_trace(self) -> None:
        """Spans from different traces do not leak."""
        put_span("trace-a", "a1", "op")
        put_span("trace-b", "b1", "op")
        assert len(get_spans("trace-a")) == 1  # type: ignore[arg-type]
        assert len(get_spans("trace-b")) == 1  # type: ignore[arg-type]

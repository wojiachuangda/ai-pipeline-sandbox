"""Structured logging with time-window query and distributed tracing (Span/Trace).

AC-1 — Structured logs
  - ``write_log`` / ``query_logs``
  - 24 h max query window → ``LOG_TIME_RANGE_EXCEEDED`` error

AC-2 — Trace / Span
  - ``put_span`` / ``get_spans`` / ``get_trace_tree``
  - Missing trace returns a NOT_FOUND error dict
"""

from __future__ import annotations

import time as _time
from typing import TypedDict

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class LogEntry(TypedDict):
    timestamp: float
    level: str
    message: str
    agent_id: str | None
    trace_id: str | None


class Span(TypedDict):
    span_id: str
    trace_id: str
    parent_span_id: str | None
    operation: str
    start_time: float
    end_time: float | None
    status: str


class TraceNode(TypedDict):
    span: Span
    children: list[TraceNode]


class TraceTree(TypedDict):
    trace_id: str
    root: TraceNode | None


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_logs: list[LogEntry] = []
_spans: dict[str, list[Span]] = {}  # trace_id → spans

_MAX_QUERY_HOURS: float = 24.0
_SECONDS_PER_HOUR: float = 3600.0

# ---------------------------------------------------------------------------
# AC-1: Structured logging
# ---------------------------------------------------------------------------


def write_log(
    level: str,
    message: str,
    agent_id: str | None = None,
    trace_id: str | None = None,
    timestamp: float | None = None,
) -> LogEntry:
    """Append a log entry and return it."""
    entry: LogEntry = {
        "timestamp": timestamp if timestamp is not None else _time.time(),
        "level": level,
        "message": message,
        "agent_id": agent_id,
        "trace_id": trace_id,
    }
    _logs.append(entry)
    return entry


def query_logs(
    start_time: float,
    end_time: float,
    level: str | None = None,
    agent_id: str | None = None,
) -> list[LogEntry] | dict:
    """Query logs within a time window and optional filters.

    Returns an error dict when ``end_time - start_time > 24 h``.
    """
    if end_time - start_time > _MAX_QUERY_HOURS * _SECONDS_PER_HOUR:
        return {
            "error": "LOG_TIME_RANGE_EXCEEDED",
            "max_hours": int(_MAX_QUERY_HOURS),
        }

    results: list[LogEntry] = []
    for entry in _logs:
        if entry["timestamp"] < start_time:
            continue
        if entry["timestamp"] > end_time:
            continue
        if level is not None and entry["level"] != level:
            continue
        if agent_id is not None and entry["agent_id"] != agent_id:
            continue
        results.append(entry)
    return results


def clear_logs() -> None:
    """Remove all logs (test helper)."""
    _logs.clear()


# ---------------------------------------------------------------------------
# AC-2: Trace / Span
# ---------------------------------------------------------------------------


def put_span(
    trace_id: str,
    span_id: str,
    operation: str,
    parent_span_id: str | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    status: str = "ok",
) -> Span:
    """Store a span under its trace_id."""
    span: Span = {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": parent_span_id,
        "operation": operation,
        "start_time": start_time if start_time is not None else _time.time(),
        "end_time": end_time,
        "status": status,
    }
    if trace_id not in _spans:
        _spans[trace_id] = []
    _spans[trace_id].append(span)
    return span


def get_spans(trace_id: str) -> list[Span] | dict:
    """Return all spans for a trace, or a NOT_FOUND error dict."""
    spans = _spans.get(trace_id)
    if spans is None or len(spans) == 0:
        return {"error": "NOT_FOUND", "detail": f"Trace {trace_id} not found"}
    return list(spans)


def get_trace_tree(trace_id: str) -> TraceTree | dict:
    """Return a nested span tree for *trace_id*, or a NOT_FOUND error dict.

    The root is the span whose ``parent_span_id`` is None.  When multiple
    root candidates exist the first is used; the rest become its siblings
    (children of a synthetic root, handled by the tree builder).
    """
    spans = _spans.get(trace_id)
    if spans is None or len(spans) == 0:
        return {"error": "NOT_FOUND", "detail": f"Trace {trace_id} not found"}

    span_map: dict[str, Span] = {s["span_id"]: s for s in spans}
    children_map: dict[str, list[str]] = {s["span_id"]: [] for s in spans}
    roots: list[str] = []

    for s in spans:
        pid = s["parent_span_id"]
        if pid is not None and pid in children_map:
            children_map[pid].append(s["span_id"])
        elif pid is not None:
            # Parent not found — treat as root
            roots.append(s["span_id"])
        else:
            roots.append(s["span_id"])

    def _build_node(span_id: str) -> TraceNode:
        return {
            "span": span_map[span_id],
            "children": [_build_node(cid) for cid in children_map.get(span_id, [])],
        }

    if not roots:
        # All spans have parents but none was listed as root — use first span
        roots = [spans[0]["span_id"]]

    root_node = _build_node(roots[0])

    # Attach additional roots as children of the root (synthetic grouping)
    for extra_root in roots[1:]:
        root_node["children"].append(_build_node(extra_root))

    return {"trace_id": trace_id, "root": root_node}


def clear_traces() -> None:
    """Remove all spans (test helper)."""
    _spans.clear()

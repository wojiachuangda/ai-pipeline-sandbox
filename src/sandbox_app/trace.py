"""ID generation and log stubs for trace correlation.

Provides UUID-based trace_id and execution_id generators, plus a logs_url
stub suitable for returning alongside execution results.
"""

from __future__ import annotations

__all__ = [
    "TraceInfo",
    "build_logs_url",
    "generate_execution_id",
    "generate_trace_id",
]

import uuid
from dataclasses import dataclass, field


def generate_trace_id() -> str:
    """Return a trace-scoped identifier.

    Format: ``"trace-"`` + 12 hex characters from a UUID4.
    """
    return "trace-" + uuid.uuid4().hex[:12]


def generate_execution_id() -> str:
    """Return an execution-scoped identifier.

    Format: ``"exec-"`` + 12 hex characters from a UUID4.
    """
    return "exec-" + uuid.uuid4().hex[:12]


def build_logs_url(execution_id: str) -> str:
    """Return a local log path stub for the given *execution_id*."""
    return f"/logs/{execution_id}.log"


@dataclass
class TraceInfo:
    """Convenience container linking trace and execution identifiers."""

    trace_id: str = field(default_factory=generate_trace_id)
    execution_id: str = field(default_factory=generate_execution_id)
    logs_url: str | None = None
    span_context: dict = field(default_factory=dict)

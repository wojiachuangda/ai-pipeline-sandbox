"""Monitoring summary API — global status plus counter stubs.

AC-4 provides a lightweight ``get_global_status()`` endpoint and in-memory
counters that other modules can bump for observability.
"""

from __future__ import annotations

import time as _time
from typing import TypedDict


class Metrics(TypedDict):
    log_count: int
    trace_count: int
    alert_count: int
    error_count: int


_start_time: float = _time.time()
_counters: Metrics = {
    "log_count": 0,
    "trace_count": 0,
    "alert_count": 0,
    "error_count": 0,
}


def get_global_status() -> dict:
    """Return a global health summary.

    >>> get_global_status()
    {'global_status': 'healthy', 'metrics': {...}, 'uptime_seconds': ...}
    """
    # Degraded/healthy heuristic — if error_count dominates we flag degraded.
    status = "healthy"
    if _counters["error_count"] > 0:
        status = "degraded"

    return {
        "global_status": status,
        "metrics": _counters.copy(),
        "uptime_seconds": _time.time() - _start_time,
    }


def increment_counter(name: str, amount: int = 1) -> None:
    """Increment a named counter.

    Supported names: ``log_count``, ``trace_count``, ``alert_count``, ``error_count``.
    Unknown names are silently ignored.
    """
    if name in _counters:
        _counters[name] += amount


def get_counters() -> Metrics:
    """Return a copy of the current counters."""
    return _counters.copy()


def reset_counters() -> None:
    """Reset all counters to zero (test helper)."""
    for key in _counters:
        _counters[key] = 0
    global _start_time
    _start_time = _time.time()

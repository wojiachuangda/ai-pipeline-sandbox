"""Tests for sandbox_app.monitoring — AC-4."""

import time

import pytest

from sandbox_app.monitoring import (
    get_counters,
    get_global_status,
    increment_counter,
    reset_counters,
)


@pytest.fixture(autouse=True)
def _clean() -> None:
    reset_counters()


class TestGlobalStatus:
    def test_returns_status_and_metrics(self) -> None:
        """AC-4.1: get_global_status contains global_status + metrics."""
        status = get_global_status()
        assert "global_status" in status
        assert "metrics" in status
        assert "uptime_seconds" in status

    def test_default_healthy(self) -> None:
        """AC-4.3: initial status is healthy."""
        status = get_global_status()
        assert status["global_status"] == "healthy"

    def test_degraded_when_errors(self) -> None:
        """Status becomes degraded when error_count > 0."""
        increment_counter("error_count")
        status = get_global_status()
        assert status["global_status"] == "degraded"


class TestCounters:
    def test_increment_and_get(self) -> None:
        """AC-4.2: increment a counter and verify via get_counters."""
        increment_counter("log_count")
        increment_counter("log_count", 2)
        counters = get_counters()
        assert counters["log_count"] == 3
        assert counters["error_count"] == 0

    def test_multiple_counters(self) -> None:
        increment_counter("log_count", 5)
        increment_counter("trace_count", 3)
        increment_counter("alert_count", 1)
        counters = get_counters()
        assert counters["log_count"] == 5
        assert counters["trace_count"] == 3
        assert counters["alert_count"] == 1

    def test_unknown_counter_silent(self) -> None:
        """Incrementing an unknown counter name does nothing."""
        increment_counter("unknown_counter")
        counters = get_counters()
        # No key added
        assert "unknown_counter" not in counters

    def test_get_counters_returns_copy(self) -> None:
        """get_counters returns a copy — mutations don't propagate."""
        counters = get_counters()
        counters["log_count"] = 999
        assert get_counters()["log_count"] == 0


class TestUptime:
    def test_uptime_positive(self) -> None:
        """uptime_seconds is a non-negative float."""
        status = get_global_status()
        assert isinstance(status["uptime_seconds"], float)
        assert status["uptime_seconds"] >= 0

    def test_uptime_grows(self) -> None:
        """uptime_seconds increases over elapsed time."""
        s1 = get_global_status()
        time.sleep(0.01)
        s2 = get_global_status()
        assert s2["uptime_seconds"] > s1["uptime_seconds"]

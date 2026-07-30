"""Tests for sandbox_app.audit — AC-5."""

import time

import pytest

from sandbox_app.audit import append_audit, clear_audit, query_audit


@pytest.fixture(autouse=True)
def _clean() -> None:
    clear_audit()


class TestAppendAudit:
    def test_append_and_query(self) -> None:
        """AC-5.1: append an entry and query it back."""
        entry = append_audit("key-1", "login", "alice", "auth-svc")
        assert isinstance(entry, dict) and "error" not in entry

        results = query_audit()
        assert len(results) == 1
        assert results[0]["key"] == "key-1"

    def test_duplicate_key_rejected(self) -> None:
        """AC-5.2: same key twice → DUPLICATE_KEY error."""
        append_audit("dup", "login", "alice", "svc")
        second = append_audit("dup", "login", "bob", "svc")
        assert isinstance(second, dict)
        assert second.get("error") == "DUPLICATE_KEY"
        assert "already exists" in second["detail"]

        # Only one entry persisted
        assert len(query_audit()) == 1


class TestQueryFilters:
    def test_filter_by_subject(self) -> None:
        """AC-5.3: filter by subject."""
        append_audit("k1", "read", "alice", "doc")
        append_audit("k2", "write", "bob", "doc")
        results = query_audit(subject="alice")
        assert len(results) == 1
        assert results[0]["key"] == "k1"

    def test_filter_by_resource(self) -> None:
        """AC-5.4: filter by resource."""
        append_audit("k1", "read", "alice", "db")
        append_audit("k2", "read", "alice", "api")
        results = query_audit(resource="api")
        assert len(results) == 1
        assert results[0]["key"] == "k2"

    def test_filter_by_time_window(self) -> None:
        """AC-5.5: filter by time range."""
        t0 = time.time()
        append_audit("k1", "read", "alice", "doc", timestamp=t0 + 10)
        append_audit("k2", "read", "bob", "doc", timestamp=t0 + 100)

        results = query_audit(start_time=t0, end_time=t0 + 50)
        assert len(results) == 1
        assert results[0]["key"] == "k1"

    def test_combined_filters(self) -> None:
        """AC-5.6: multi-field combined filter (AND)."""
        append_audit("k1", "login", "alice", "auth")
        append_audit("k2", "login", "bob", "auth")
        append_audit("k3", "logout", "alice", "auth")

        results = query_audit(subject="alice", action="login", resource="auth")
        assert len(results) == 1
        assert results[0]["key"] == "k1"

    def test_filter_by_action(self) -> None:
        append_audit("k1", "delete", "alice", "file")
        append_audit("k2", "create", "alice", "file")
        results = query_audit(action="delete")
        assert len(results) == 1
        assert results[0]["key"] == "k1"

    def test_empty_result(self) -> None:
        append_audit("k1", "read", "alice", "doc")
        assert query_audit(subject="nonexistent") == []

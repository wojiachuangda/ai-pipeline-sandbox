"""Immutable append-only audit log.

Every audit entry carries a unique ``key``.  Once written a key cannot be
overwritten — the API returns an error dict to maintain audit-chain
integrity.
"""

from __future__ import annotations

import time as _time
from typing import TypedDict


class AuditEntry(TypedDict):
    audit_id: str
    key: str
    action: str
    subject: str
    resource: str
    timestamp: float
    metadata: dict | None


_entries: list[AuditEntry] = []
_seen_keys: set[str] = set()
_counter: int = 0


def _next_id() -> str:
    global _counter
    _counter += 1
    return f"audit-{_counter}"


def append_audit(
    key: str,
    action: str,
    subject: str,
    resource: str,
    metadata: dict | None = None,
    timestamp: float | None = None,
) -> AuditEntry | dict:
    """Append an audit entry.  Returns an error dict if *key* already exists.

    >>> append_audit("req-1", "login", "alice", "auth-service")
    {'audit_id': 'audit-1', 'key': 'req-1', ...}
    >>> append_audit("req-1", "login", "alice", "auth-service")
    {'error': 'DUPLICATE_KEY', ...}
    """
    if key in _seen_keys:
        return {
            "error": "DUPLICATE_KEY",
            "detail": f"Audit entry with key '{key}' already exists. Audit is append-only.",
        }

    entry: AuditEntry = {
        "audit_id": _next_id(),
        "key": key,
        "action": action,
        "subject": subject,
        "resource": resource,
        "timestamp": timestamp if timestamp is not None else _time.time(),
        "metadata": metadata,
    }
    _entries.append(entry)
    _seen_keys.add(key)
    return entry


def query_audit(
    subject: str | None = None,
    resource: str | None = None,
    action: str | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
) -> list[AuditEntry]:
    """Query audit entries with optional filters.

    All filters are combined with AND.
    """
    results = _entries
    if subject is not None:
        results = [e for e in results if e["subject"] == subject]
    if resource is not None:
        results = [e for e in results if e["resource"] == resource]
    if action is not None:
        results = [e for e in results if e["action"] == action]
    if start_time is not None:
        results = [e for e in results if e["timestamp"] >= start_time]
    if end_time is not None:
        results = [e for e in results if e["timestamp"] <= end_time]
    return results


def clear_audit() -> None:
    """Remove all audit entries (test helper)."""
    _entries.clear()
    _seen_keys.clear()
    global _counter
    _counter = 0

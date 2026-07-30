"""Core helpers for the sandbox app."""

from __future__ import annotations


def health() -> dict[str, str]:
    """Return service health payload."""
    return {"status": "ok"}


def ping() -> dict[str, str]:
    """Simple readiness probe."""
    return {"pong": "true"}


def version() -> dict[str, str]:
    """Return application version."""
    return {"version": "0.1.0"}

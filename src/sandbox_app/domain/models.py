"""Domain models — enums and value objects for the sandbox platform.

Defines the foundational types that all other layers depend on:
Role, Tenant context, and a unified ErrorCode structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Role(str, Enum):
    """Named roles for platform actors.

    Uses StrEnum so values serialize directly for HTTP bodies and databases.
    """

    ADMIN = "admin"
    AGENT = "agent"
    OBSERVER = "observer"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tenant:
    """Lightweight tenant context — immutable value object.

    Attrs:
        tenant_id: Machine-readable tenant identifier.
        name: Human-readable tenant display name.
    """

    tenant_id: str
    name: str


@dataclass(frozen=True)
class ErrorCode:
    """Unified error-code structure.

    Attrs:
        code: Machine-readable slug (e.g. ``"NOT_FOUND"``).
        message: Human-readable description (e.g. ``"Resource not found"``).
    """

    code: str
    message: str

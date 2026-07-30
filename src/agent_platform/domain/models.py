"""Core domain enumerations and value objects (goal.md §1.2 / NFR baseline)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    """Standard platform roles from PRD §1.2."""

    ADMIN = "R-ADMIN"
    DEV = "R-DEV"
    OPS = "R-OPS"
    AUDIT = "R-AUDIT"


class ErrorCode(StrEnum):
    """Stable API error codes used across modules."""

    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    AGENT_NAME_DUPLICATE = "AGENT_NAME_DUPLICATE"
    INVALID_STATUS_TRANSITION = "INVALID_STATUS_TRANSITION"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class ApiError:
    """Uniform error payload: machine code + human message (+ optional details)."""

    code: ErrorCode
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": str(self.code), "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Request-scoped tenant + actor (OIDC subject stub for later)."""

    tenant_id: str
    actor_id: str
    roles: tuple[Role, ...] = ()

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.actor_id.strip():
            raise ValueError("actor_id is required")

    def has_role(self, role: Role) -> bool:
        return role in self.roles

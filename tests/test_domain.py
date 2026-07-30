"""Unit tests for domain models — enums, error codes, and tenant context."""

from __future__ import annotations

import pytest

from sandbox_app.domain import ErrorCode, Role, Tenant


# ---------------------------------------------------------------------------
# Role enum
# ---------------------------------------------------------------------------


def test_role_enum_values() -> None:
    """Every defined Role member matches its expected string value."""
    assert Role.ADMIN == "admin"
    assert Role.AGENT == "agent"
    assert Role.OBSERVER == "observer"


def test_role_enum_membership() -> None:
    """Membership check works as expected for str-based enum."""
    assert Role("admin") is Role.ADMIN
    assert Role("agent") is Role.AGENT
    assert Role("observer") is Role.OBSERVER

    with pytest.raises(ValueError):
        Role("superadmin")  # not a defined member


# ---------------------------------------------------------------------------
# ErrorCode
# ---------------------------------------------------------------------------


def test_error_code_structure() -> None:
    """ErrorCode holds a machine-readable code and human-readable message."""
    err = ErrorCode(code="NOT_FOUND", message="Resource not found")
    assert err.code == "NOT_FOUND"
    assert err.message == "Resource not found"


def test_error_code_immutable() -> None:
    """Frozen dataclass prevents field mutation."""
    err = ErrorCode(code="E001", message="Something went wrong")
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        err.code = "E002"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------


def test_tenant_creation() -> None:
    """Tenant value object is constructed with tenant_id and name."""
    t = Tenant(tenant_id="t-abc", name="Acme Corp")
    assert t.tenant_id == "t-abc"
    assert t.name == "Acme Corp"


def test_tenant_immutable() -> None:
    """Frozen dataclass prevents field mutation on Tenant."""
    t = Tenant(tenant_id="t-xyz", name="Beta Inc")
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        t.name = "Gamma LLC"  # type: ignore[misc]

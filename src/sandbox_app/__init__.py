"""Sandbox application package."""

from .compatibility import CompatibilityReport, CompatibilityResult, IncompatibleItem, check_compatibility
from .core import health, ping
from .registry import (
    Dependency,
    DependencyType,
    FakeClock,
    Instance,
    InstanceStatus,
    Registry,
    RegistryConfig,
    ResolutionState,
    version_satisfies,
)

__all__ = [
    "health",
    "ping",
    "Registry",
    "RegistryConfig",
    "Instance",
    "InstanceStatus",
    "Dependency",
    "DependencyType",
    "ResolutionState",
    "FakeClock",
    "CompatibilityReport",
    "CompatibilityResult",
    "IncompatibleItem",
    "check_compatibility",
    "version_satisfies",
]

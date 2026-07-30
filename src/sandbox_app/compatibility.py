"""Compatibility checker for the registry."""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from enum import Enum

from .registry import Instance, InstanceStatus, Registry, version_satisfies


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class CompatibilityResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


@dataclass
class IncompatibleItem:
    instance_id: str
    dep_name: str
    required_version: str
    actual_version: str | None
    reason: str  # "missing_dependency" | "version_mismatch" | "circular_dependency" | "unhealthy"


@dataclass
class CompatibilityReport:
    result: CompatibilityResult
    incompatible_items: list[IncompatibleItem] = field(default_factory=list)
    checked_instance_id: str = ""
    timestamp: float = field(default_factory=lambda: _time.monotonic())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_compatibility(
    instance_id: str,
    registry: Registry,
) -> CompatibilityReport:
    """Evaluate whether *instance_id* can safely activate against *registry*.

    Returns a ``CompatibilityReport`` whose ``result`` is one of:

    * ``PASS`` — all dependencies satisfied.
    * ``FAIL`` — hard blockers: missing dep, version mismatch, circular dep.
    * ``WARNING`` — soft issues like unhealthy dependents.
    """
    items: list[IncompatibleItem] = []

    inst: Instance | None = registry.get(instance_id)
    if inst is None:
        return CompatibilityReport(
            result=CompatibilityResult.FAIL,
            incompatible_items=[
                IncompatibleItem(
                    instance_id=instance_id,
                    dep_name="",
                    required_version="",
                    actual_version=None,
                    reason="missing_instance",
                )
            ],
            checked_instance_id=instance_id,
        )

    # 1. Check own health
    if inst.status == InstanceStatus.UNHEALTHY:
        items.append(
            IncompatibleItem(
                instance_id=instance_id,
                dep_name=inst.name,
                required_version="",
                actual_version=inst.version,
                reason="unhealthy",
            )
        )

    # 2. Check circular dependency
    cycle = registry.check_circular(instance_id)
    if cycle is not None:
        items.append(
            IncompatibleItem(
                instance_id=instance_id,
                dep_name=" → ".join(cycle),
                required_version="",
                actual_version=None,
                reason="circular_dependency",
            )
        )

    # 3. Check every declared dependency
    _collect_dep_issues(instance_id, inst, registry, items, seen=None)

    # Determine overall result
    if not items:
        result = CompatibilityResult.PASS
    elif any(
        it.reason in ("missing_instance", "missing_dependency", "version_mismatch", "circular_dependency")
        for it in items
    ):
        result = CompatibilityResult.FAIL
    else:
        result = CompatibilityResult.WARNING

    return CompatibilityReport(
        result=result,
        incompatible_items=items,
        checked_instance_id=instance_id,
    )


def _collect_dep_issues(
    instance_id: str,
    inst: Instance,
    registry: Registry,
    items: list[IncompatibleItem],
    seen: set[str] | None,
) -> None:
    """Recursively check direct + transitive dependencies for issues."""
    if seen is None:
        seen = set()

    for dep in inst.depends_on:
        target = registry.get(dep.name)
        if target is None:
            items.append(
                IncompatibleItem(
                    instance_id=instance_id,
                    dep_name=dep.name,
                    required_version=dep.version_constraint,
                    actual_version=None,
                    reason="missing_dependency",
                )
            )
            continue

        if not version_satisfies(target.version, dep.version_constraint):
            items.append(
                IncompatibleItem(
                    instance_id=instance_id,
                    dep_name=dep.name,
                    required_version=dep.version_constraint,
                    actual_version=target.version,
                    reason="version_mismatch",
                )
            )

        # Recurse into transitive deps (guard against cycles already
        # reported above — just avoid infinite recursion here).
        if dep.name not in seen:
            seen.add(dep.name)
            _collect_dep_issues(instance_id, target, registry, items, seen)

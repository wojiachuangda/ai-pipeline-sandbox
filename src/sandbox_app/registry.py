"""Registry — instance registration, heartbeat, dependency management."""

from __future__ import annotations

import re
import time as _time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class InstanceStatus(Enum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    DEREGISTERED = "DEREGISTERED"


class DependencyType(Enum):
    SERVICE = "SERVICE"
    AGENT = "AGENT"
    PLUGIN = "PLUGIN"


class ResolutionState(Enum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class Dependency:
    dep_type: DependencyType
    name: str
    version_constraint: str  # e.g. ">=1.0", "==2.1.3"


@dataclass
class Instance:
    id: str
    name: str
    type: str  # "SERVICE" | "AGENT" | "PLUGIN"
    version: str
    depends_on: list[Dependency] = field(default_factory=list)
    status: InstanceStatus = InstanceStatus.HEALTHY
    last_heartbeat: float = field(default_factory=lambda: _time.monotonic())
    consecutive_failures: int = 0


# ---------------------------------------------------------------------------
# Registry config
# ---------------------------------------------------------------------------

@dataclass
class RegistryConfig:
    heartbeat_timeout: float = 30.0  # seconds: exceed → UNHEALTHY
    max_consecutive_failures: int = 3  # consecutive timeouts → DEREGISTERED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeClock:
    """Controllable clock for tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


# ---------------------------------------------------------------------------
# Version constraint parsing
# ---------------------------------------------------------------------------

_VCOMP_RE = re.compile(r"^(>=|<=|==|>|<|!=)(.+)$")


def _parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def _pad_versions(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Pad shorter version tuple with zeros so they compare correctly."""
    max_len = max(len(a), len(b))
    return (
        a + (0,) * (max_len - len(a)),
        b + (0,) * (max_len - len(b)),
    )


def version_satisfies(actual: str, constraint: str) -> bool:
    """Check whether *actual* version satisfies *constraint* (e.g. ">=1.0")."""
    m = _VCOMP_RE.match(constraint)
    if not m:
        raise ValueError(f"Invalid version constraint: {constraint!r}")
    op, target = m.group(1), m.group(2)
    a, t = _pad_versions(_parse_version(actual), _parse_version(target))
    if op == ">=":
        return a >= t
    if op == "<=":
        return a <= t
    if op == "==":
        return a == t
    if op == ">":
        return a > t
    if op == "<":
        return a < t
    if op == "!=":
        return a != t
    raise ValueError(f"Unknown operator: {op!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class Registry:
    """In-memory registry with heartbeat, dependency, and cycle detection."""

    def __init__(
        self,
        config: RegistryConfig | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.config = config or RegistryConfig()
        self._clock = clock or _time.monotonic
        self._instances: dict[str, Instance] = {}

    # ---- basic CRUD -------------------------------------------------------

    def register(self, instance: Instance) -> None:
        """Register (or overwrite) an instance."""
        instance.last_heartbeat = self._clock()
        self._instances[instance.id] = instance

    def heartbeat(self, instance_id: str) -> bool:
        """Refresh heartbeat timestamp. Returns False if instance unknown."""
        inst = self._instances.get(instance_id)
        if inst is None:
            return False
        inst.last_heartbeat = self._clock()
        inst.consecutive_failures = 0
        if inst.status == InstanceStatus.UNHEALTHY:
            inst.status = InstanceStatus.HEALTHY
        return True

    def deregister(self, instance_id: str) -> None:
        """Remove an instance (idempotent)."""
        self._instances.pop(instance_id, None)

    def get(self, instance_id: str) -> Instance | None:
        """Return an instance by id or None."""
        return self._instances.get(instance_id)

    # ---- health -----------------------------------------------------------

    def check_health(self) -> dict[str, list[Instance]]:
        """Walk all instances and update status based on heartbeat timeout.

        Returns a dict with keys ``healthy``, ``unhealthy``, ``deregistered``.
        """
        now = self._clock()
        healthy: list[Instance] = []
        unhealthy: list[Instance] = []
        deregistered: list[Instance] = []

        for inst in list(self._instances.values()):
            elapsed = now - inst.last_heartbeat
            if elapsed > self.config.heartbeat_timeout:
                inst.consecutive_failures += 1
                inst.status = InstanceStatus.UNHEALTHY
                if inst.consecutive_failures >= self.config.max_consecutive_failures:
                    # deregister — remove from in-memory table
                    inst.status = InstanceStatus.DEREGISTERED
                    self._instances.pop(inst.id, None)
                    deregistered.append(inst)
                else:
                    unhealthy.append(inst)
            else:
                inst.status = InstanceStatus.HEALTHY
                inst.consecutive_failures = 0
                healthy.append(inst)

        return {
            "healthy": healthy,
            "unhealthy": unhealthy,
            "deregistered": deregistered,
        }

    # ---- dependencies -----------------------------------------------------

    def add_dependency(self, instance_id: str, dep: Dependency) -> None:
        """Append a dependency declaration to an instance."""
        inst = self._instances.get(instance_id)
        if inst is None:
            raise KeyError(f"Unknown instance: {instance_id!r}")
        inst.depends_on.append(dep)

    def check_circular(self, instance_id: str) -> list[str] | None:
        """Detect a cycle starting from *instance_id*.

        Uses DFS with a visited-and-on-stack colour set to find a back edge.
        Returns the cycle path (list of instance ids) if found, else ``None``.
        """
        if instance_id not in self._instances:
            return None

        WHITE, GRAY, BLACK = 0, 1, 2
        colour: dict[str, int] = {}
        parent: dict[str, str | None] = {}

        def _dfs(u: str) -> list[str] | None:
            colour[u] = GRAY
            inst = self._instances.get(u)
            if inst is not None:
                for dep in inst.depends_on:
                    v = dep.name
                    if v not in self._instances:
                        continue  # external dep — can't form a registered cycle
                    c = colour.get(v, WHITE)
                    if c == GRAY:
                        # back edge found → build cycle path
                        path: list[str] = [v, u]
                        cur = u
                        while parent.get(cur) is not None and parent[cur] != v:
                            cur = parent[cur]  # type: ignore[assignment]
                            path.append(cur)
                        path.append(v)
                        path.reverse()
                        return path
                    if c == WHITE:
                        parent[v] = u
                        result = _dfs(v)
                        if result is not None:
                            return result
            colour[u] = BLACK
            return None

        return _dfs(instance_id)

    def resolve_dependencies(self, instance_id: str) -> ResolutionState:
        """Check that every transitive dependency is registered and version-satisfied.

        Returns ``RESOLVED`` when all constraints pass, otherwise ``UNRESOLVED``.
        """
        inst = self._instances.get(instance_id)
        if inst is None:
            return ResolutionState.UNRESOLVED

        seen: set[str] = set()
        stack: list[Dependency] = list(inst.depends_on)

        while stack:
            dep = stack.pop()
            if dep.name in seen:
                continue
            seen.add(dep.name)

            target = self._instances.get(dep.name)
            if target is None:
                return ResolutionState.UNRESOLVED
            if not version_satisfies(target.version, dep.version_constraint):
                return ResolutionState.UNRESOLVED
            # push transitive deps
            stack.extend(target.depends_on)

        return ResolutionState.RESOLVED

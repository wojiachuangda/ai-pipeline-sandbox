"""Tests for registry.py — AC-1, AC-2, AC-4, AC-5."""

import pytest

from sandbox_app import (
    Dependency,
    DependencyType,
    FakeClock,
    Instance,
    InstanceStatus,
    Registry,
    RegistryConfig,
    ResolutionState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc(
    sid: str,
    name: str | None = None,
    version: str = "1.0.0",
    type_: str = "SERVICE",
    deps: list[Dependency] | None = None,
) -> Instance:
    return Instance(
        id=sid,
        name=name or sid,
        type=type_,
        version=version,
        depends_on=deps or [],
    )


# ---------------------------------------------------------------------------
# AC-1: register / heartbeat / deregister
# ---------------------------------------------------------------------------

class TestRegisterDeregister:
    def test_register_instance(self) -> None:
        reg = Registry()
        inst = _svc("a")
        reg.register(inst)
        assert reg.get("a") is inst

    def test_heartbeat_updates_timestamp(self) -> None:
        clock = FakeClock(100.0)
        reg = Registry(clock=clock)
        inst = _svc("a")
        inst.last_heartbeat = 0.0
        reg.register(inst)

        assert reg.heartbeat("a") is True
        assert inst.last_heartbeat == 100.0
        assert inst.consecutive_failures == 0

    def test_heartbeat_nonexistent_returns_false(self) -> None:
        reg = Registry()
        assert reg.heartbeat("ghost") is False

    def test_heartbeat_restores_healthy_from_unhealthy(self) -> None:
        clock = FakeClock(0.0)
        reg = Registry(clock=clock)
        inst = Instance(id="a", name="a", type="SERVICE", version="1.0")
        inst.status = InstanceStatus.UNHEALTHY
        inst.consecutive_failures = 2
        reg.register(inst)

        reg.heartbeat("a")
        assert inst.status == InstanceStatus.HEALTHY
        assert inst.consecutive_failures == 0

    def test_deregister_removes_instance(self) -> None:
        reg = Registry()
        reg.register(_svc("a"))
        reg.deregister("a")
        assert reg.get("a") is None

    def test_deregister_idempotent(self) -> None:
        reg = Registry()
        reg.deregister("x")  # no-op
        reg.deregister("x")  # still no-op


# ---------------------------------------------------------------------------
# AC-1 + AC-5: heartbeat timeout → UNHEALTHY → DEREGISTERED
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_check_marks_unhealthy_on_timeout(self) -> None:
        clock = FakeClock(0.0)
        reg = Registry(
            config=RegistryConfig(heartbeat_timeout=30.0, max_consecutive_failures=3),
            clock=clock,
        )
        inst = _svc("a")
        reg.register(inst)
        # initial heartbeat is at t=0; advance past timeout
        clock.advance(31.0)

        result = reg.check_health()
        assert inst.status == InstanceStatus.UNHEALTHY
        assert inst.consecutive_failures == 1
        assert inst in result["unhealthy"]

    def test_health_check_deregisters_after_consecutive_failures(self) -> None:
        clock = FakeClock(0.0)
        reg = Registry(
            config=RegistryConfig(heartbeat_timeout=30.0, max_consecutive_failures=3),
            clock=clock,
        )
        inst = _svc("a")
        reg.register(inst)

        for i in range(3):
            clock.advance(31.0)
            result = reg.check_health()
            if i < 2:
                assert inst.status == InstanceStatus.UNHEALTHY
            else:
                assert inst.status == InstanceStatus.DEREGISTERED
                assert reg.get("a") is None
                assert inst in result["deregistered"]

    def test_health_check_resets_on_heartbeat(self) -> None:
        clock = FakeClock(0.0)
        reg = Registry(clock=clock)
        inst = _svc("a")
        reg.register(inst)

        # first timeout
        clock.advance(31.0)
        reg.check_health()
        assert inst.consecutive_failures == 1

        # heartbeat before second timeout
        reg.heartbeat("a")
        assert inst.consecutive_failures == 0
        assert inst.status == InstanceStatus.HEALTHY

    def test_health_check_stays_healthy_within_timeout(self) -> None:
        clock = FakeClock(0.0)
        reg = Registry(clock=clock)
        inst = _svc("a")
        reg.register(inst)

        clock.advance(29.0)
        result = reg.check_health()
        assert inst.status == InstanceStatus.HEALTHY
        assert inst in result["healthy"]


# ---------------------------------------------------------------------------
# AC-2: add_dependency
# ---------------------------------------------------------------------------

class TestAddDependency:
    def test_add_dependency(self) -> None:
        reg = Registry()
        inst = _svc("a")
        reg.register(inst)

        dep = Dependency(dep_type=DependencyType.SERVICE, name="b", version_constraint=">=1.0")
        reg.add_dependency("a", dep)
        assert inst.depends_on == [dep]

    def test_add_dependency_unknown_instance_raises(self) -> None:
        reg = Registry()
        dep = Dependency(dep_type=DependencyType.SERVICE, name="b", version_constraint=">=1.0")
        with pytest.raises(KeyError, match="ghost"):
            reg.add_dependency("ghost", dep)


# ---------------------------------------------------------------------------
# AC-2 + AC-5: circular dependency detection
# ---------------------------------------------------------------------------

class TestCircularDependency:
    def test_circular_dependency_direct(self) -> None:
        reg = Registry()
        a = _svc("a", deps=[Dependency(DependencyType.SERVICE, "b", ">=1.0")])
        b = _svc("b", deps=[Dependency(DependencyType.SERVICE, "a", ">=1.0")])
        reg.register(a)
        reg.register(b)

        cycle = reg.check_circular("a")
        assert cycle is not None
        assert "a" in cycle
        assert "b" in cycle
        assert cycle[0] == cycle[-1]  # closed loop

    def test_circular_dependency_indirect(self) -> None:
        reg = Registry()
        a = _svc("a", deps=[Dependency(DependencyType.SERVICE, "b", ">=1.0")])
        b = _svc("b", deps=[Dependency(DependencyType.SERVICE, "c", ">=1.0")])
        c = _svc("c", deps=[Dependency(DependencyType.SERVICE, "a", ">=1.0")])
        reg.register(a)
        reg.register(b)
        reg.register(c)

        cycle = reg.check_circular("a")
        assert cycle is not None
        assert cycle[0] == cycle[-1]
        assert set(cycle[:-1]) == {"a", "b", "c"}

    def test_no_circular_dependency(self) -> None:
        reg = Registry()
        a = _svc("a", deps=[Dependency(DependencyType.SERVICE, "b", ">=1.0")])
        b = _svc("b", deps=[Dependency(DependencyType.SERVICE, "c", ">=1.0")])
        c = _svc("c", deps=[])
        reg.register(a)
        reg.register(b)
        reg.register(c)

        assert reg.check_circular("a") is None

    def test_circular_unknown_instance_returns_none(self) -> None:
        reg = Registry()
        assert reg.check_circular("ghost") is None

    def test_circular_with_external_dep_no_cycle(self) -> None:
        """External (unregistered) deps are ignored for cycle detection."""
        reg = Registry()
        a = _svc("a", deps=[Dependency(DependencyType.SERVICE, "external-lib", ">=1.0")])
        reg.register(a)
        assert reg.check_circular("a") is None


# ---------------------------------------------------------------------------
# AC-4: dependency resolution
# ---------------------------------------------------------------------------

class TestResolveDependencies:
    def test_resolve_dependencies_all_resolved(self) -> None:
        reg = Registry()
        a = _svc("a", version="1.0", deps=[Dependency(DependencyType.SERVICE, "b", ">=1.0")])
        b = _svc("b", version="2.0")
        reg.register(a)
        reg.register(b)

        assert reg.resolve_dependencies("a") == ResolutionState.RESOLVED

    def test_resolve_dependencies_missing_dep(self) -> None:
        reg = Registry()
        a = _svc("a", deps=[Dependency(DependencyType.SERVICE, "b", ">=1.0")])
        reg.register(a)
        # "b" not registered
        assert reg.resolve_dependencies("a") == ResolutionState.UNRESOLVED

    def test_resolve_dependencies_version_mismatch(self) -> None:
        reg = Registry()
        a = _svc("a", deps=[Dependency(DependencyType.SERVICE, "b", ">=2.0")])
        b = _svc("b", version="1.0")
        reg.register(a)
        reg.register(b)

        assert reg.resolve_dependencies("a") == ResolutionState.UNRESOLVED

    def test_resolve_dependencies_transitive(self) -> None:
        reg = Registry()
        a = _svc("a", deps=[Dependency(DependencyType.SERVICE, "b", ">=1.0")])
        b = _svc("b", version="1.5", deps=[Dependency(DependencyType.PLUGIN, "c", "==3.0")])
        c = _svc("c", version="3.0", type_="PLUGIN")
        reg.register(a)
        reg.register(b)
        reg.register(c)

        assert reg.resolve_dependencies("a") == ResolutionState.RESOLVED

    def test_resolve_dependencies_unknown_instance(self) -> None:
        reg = Registry()
        assert reg.resolve_dependencies("ghost") == ResolutionState.UNRESOLVED


# ---------------------------------------------------------------------------
# version_satisfies helper
# ---------------------------------------------------------------------------

class TestVersionSatisfies:
    @pytest.mark.parametrize(
        "actual, constraint, expected",
        [
            ("1.0.0", ">=1.0", True),
            ("0.9.0", ">=1.0", False),
            ("2.0.0", ">=1.0", True),
            ("1.0.0", "<=1.0", True),
            ("1.0.0", "<=2.0", True),
            ("2.0.0", "<=1.0", False),
            ("1.0.0", "==1.0", True),
            ("2.0.0", "==1.0", False),
            ("1.0.0", ">0.9", True),
            ("0.9.0", ">1.0", False),
            ("1.0.0", "<2.0", True),
            ("2.0.0", "<2.0", False),
            ("1.0.0", "!=2.0", True),
            ("1.0.0", "!=1.0", False),
            ("3.2.1", ">=3.0", True),
            ("3.2.1", "<=3.2.1", True),
            ("3.2.1", "==3.2.1", True),
            ("3.2.1", ">3.2.0", True),
            ("3.2.1", "<3.3", True),
            ("3.2.1", "!=3.2.0", True),
        ],
    )
    def test_version_satisfies(self, actual: str, constraint: str, expected: bool) -> None:
        from sandbox_app import version_satisfies

        assert version_satisfies(actual, constraint) == expected

    def test_version_satisfies_invalid_constraint(self) -> None:
        from sandbox_app import version_satisfies

        with pytest.raises(ValueError, match="Invalid version constraint"):
            version_satisfies("1.0", "~=1.0")

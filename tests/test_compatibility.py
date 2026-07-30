"""Tests for compatibility.py — AC-3, AC-5."""

from sandbox_app import (
    CompatibilityResult,
    Dependency,
    DependencyType,
    FakeClock,
    Instance,
    Registry,
    check_compatibility,
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
# AC-3
# ---------------------------------------------------------------------------

class TestCompatibilityPass:
    def test_compatibility_pass(self) -> None:
        reg = Registry()
        a = _svc("a", deps=[Dependency(DependencyType.SERVICE, "b", ">=1.0")])
        b = _svc("b", version="2.0")
        reg.register(a)
        reg.register(b)

        report = check_compatibility("a", reg)
        assert report.result == CompatibilityResult.PASS
        assert report.incompatible_items == []
        assert report.checked_instance_id == "a"
        assert report.timestamp > 0


class TestCompatibilityFail:
    def test_compatibility_fail_missing_dep(self) -> None:
        reg = Registry()
        a = _svc("a", deps=[Dependency(DependencyType.SERVICE, "b", ">=1.0")])
        reg.register(a)

        report = check_compatibility("a", reg)
        assert report.result == CompatibilityResult.FAIL
        assert any(it.reason == "missing_dependency" for it in report.incompatible_items)

    def test_compatibility_fail_circular(self) -> None:
        reg = Registry()
        a = _svc("a", deps=[Dependency(DependencyType.SERVICE, "b", ">=1.0")])
        b = _svc("b", deps=[Dependency(DependencyType.SERVICE, "a", ">=1.0")])
        reg.register(a)
        reg.register(b)

        report = check_compatibility("a", reg)
        assert report.result == CompatibilityResult.FAIL
        assert any(it.reason == "circular_dependency" for it in report.incompatible_items)

    def test_compatibility_fail_missing_instance(self) -> None:
        reg = Registry()
        report = check_compatibility("ghost", reg)
        assert report.result == CompatibilityResult.FAIL
        assert any(it.reason == "missing_instance" for it in report.incompatible_items)

    def test_compatibility_fail_version_mismatch(self) -> None:
        reg = Registry()
        a = _svc("a", deps=[Dependency(DependencyType.SERVICE, "b", ">=3.0")])
        b = _svc("b", version="1.0")
        reg.register(a)
        reg.register(b)

        report = check_compatibility("a", reg)
        assert report.result == CompatibilityResult.FAIL
        assert any(it.reason == "version_mismatch" for it in report.incompatible_items)


class TestCompatibilityWarning:
    def test_compatibility_warning_unhealthy(self) -> None:
        clock = FakeClock(0.0)
        reg = Registry(clock=clock)
        a = _svc("a")
        reg.register(a)
        # push past timeout to make it unhealthy
        clock.advance(31.0)
        reg.check_health()

        report = check_compatibility("a", reg)
        assert report.result in (CompatibilityResult.WARNING, CompatibilityResult.FAIL)
        assert any(it.reason == "unhealthy" for it in report.incompatible_items)


class TestCompatibilityReportStructure:
    def test_compatibility_result_structure(self) -> None:
        """AC-5: verify report contains all required fields."""
        reg = Registry()
        a = _svc("a")
        reg.register(a)

        report = check_compatibility("a", reg)
        assert report.result == CompatibilityResult.PASS
        assert isinstance(report.incompatible_items, list)
        assert report.checked_instance_id == "a"
        assert isinstance(report.timestamp, float)
        assert report.timestamp > 0

    def test_compatibility_multiple_incompatible_items(self) -> None:
        reg = Registry()
        a = _svc("a", deps=[
            Dependency(DependencyType.SERVICE, "b", ">=1.0"),
            Dependency(DependencyType.SERVICE, "c", ">=1.0"),
        ])
        reg.register(a)
        # neither b nor c registered

        report = check_compatibility("a", reg)
        assert report.result == CompatibilityResult.FAIL
        missing = [it for it in report.incompatible_items if it.reason == "missing_dependency"]
        assert len(missing) == 2
        names = {it.dep_name for it in missing}
        assert names == {"b", "c"}

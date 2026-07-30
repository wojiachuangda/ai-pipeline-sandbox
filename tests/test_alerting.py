"""Tests for sandbox_app.alerting — AC-3."""

import pytest

from sandbox_app.alerting import (
    clear_rules,
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    update_rule,
)


@pytest.fixture(autouse=True)
def _clean() -> None:
    clear_rules()


class TestCRUD:
    def test_create_and_get(self) -> None:
        """AC-3.1: create a rule and retrieve it."""
        rule = create_rule(
            metric="cpu_usage",
            condition="> 90",
            severity="critical",
            notification_channels=["email", "slack"],
        )
        assert rule["metric"] == "cpu_usage"
        assert rule["severity"] == "critical"

        got = get_rule(rule["id"])
        assert got is not None
        assert got["id"] == rule["id"]

    def test_update_rule(self) -> None:
        """Update an existing rule's fields."""
        rule = create_rule("mem", "> 80", "warning", ["email"])
        updated = update_rule(rule["id"], severity="critical", condition="> 95")
        assert updated is not None
        assert updated["severity"] == "critical"
        assert updated["condition"] == "> 95"
        # Unchanged fields preserved
        assert updated["metric"] == "mem"

    def test_delete_rule(self) -> None:
        """Delete a rule and verify it's gone."""
        rule = create_rule("disk", "> 95", "critical", ["pagerduty"])
        assert delete_rule(rule["id"]) is True
        assert get_rule(rule["id"]) is None

    def test_full_crud_cycle(self) -> None:
        """AC-3.1: full CRUD lifecycle."""
        # Create
        rule = create_rule(
            metric="error_rate",
            condition="> 0.05",
            severity="warning",
            notification_channels=["email"],
        )
        rid = rule["id"]

        # Read
        assert get_rule(rid) is not None

        # Update
        update_rule(rid, severity="critical")
        assert get_rule(rid)["severity"] == "critical"

        # Delete
        assert delete_rule(rid) is True
        assert get_rule(rid) is None


class TestListRules:
    def test_list_all(self) -> None:
        """AC-3.2: list all rules."""
        create_rule("cpu", "> 90", "critical", ["email"])
        create_rule("mem", "> 80", "warning", ["slack"])
        assert len(list_rules()) == 2

    def test_filter_by_severity(self) -> None:
        """AC-3.5: filter by severity."""
        create_rule("cpu", "> 90", "critical", ["email"])
        create_rule("mem", "> 80", "warning", ["slack"])
        create_rule("disk", "> 95", "critical", ["pagerduty"])

        critical = list_rules(severity="critical")
        assert len(critical) == 2

        info = list_rules(severity="info")
        assert info == []


class TestEdgeCases:
    def test_delete_nonexistent(self) -> None:
        """AC-3.3: delete nonexistent returns False."""
        assert delete_rule("nope") is False

    def test_update_nonexistent(self) -> None:
        """AC-3.4: update nonexistent returns None."""
        assert update_rule("nope", severity="critical") is None

    def test_get_nonexistent(self) -> None:
        assert get_rule("nope") is None

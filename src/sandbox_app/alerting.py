"""Alert rule CRUD with in-memory storage.

Each rule carries: metric name, condition expression, severity, and a list
of notification channels.
"""

from __future__ import annotations

from typing import TypedDict


class AlertRule(TypedDict):
    id: str
    metric: str
    condition: str
    severity: str
    notification_channels: list[str]
    enabled: bool


_rules: dict[str, AlertRule] = {}
_counter: int = 0


def _next_id() -> str:
    global _counter
    _counter += 1
    return f"rule-{_counter}"


def create_rule(
    metric: str,
    condition: str,
    severity: str,
    notification_channels: list[str] | None = None,
    enabled: bool = True,
) -> AlertRule:
    """Create a new alert rule."""
    rule: AlertRule = {
        "id": _next_id(),
        "metric": metric,
        "condition": condition,
        "severity": severity,
        "notification_channels": notification_channels or [],
        "enabled": enabled,
    }
    _rules[rule["id"]] = rule
    return rule


def get_rule(rule_id: str) -> AlertRule | None:
    """Retrieve a rule by id, or None."""
    return _rules.get(rule_id)


def list_rules(severity: str | None = None) -> list[AlertRule]:
    """List all rules, optionally filtered by severity."""
    result = list(_rules.values())
    if severity is not None:
        result = [r for r in result if r["severity"] == severity]
    return result


def update_rule(rule_id: str, **fields: object) -> AlertRule | None:
    """Update fields of an existing rule.  Returns the updated rule or None."""
    rule = _rules.get(rule_id)
    if rule is None:
        return None
    for key, value in fields.items():
        if key in rule:
            rule[key] = value  # type: ignore[literal-required]
    return rule


def delete_rule(rule_id: str) -> bool:
    """Remove a rule.  Returns True if it existed."""
    if rule_id in _rules:
        del _rules[rule_id]
        return True
    return False


def clear_rules() -> None:
    """Remove all rules (test helper)."""
    _rules.clear()
    global _counter
    _counter = 0

"""Compliance policy configuration storage.

Manages RETENTION and MASKING policy types with built-in defaults.

- **RETENTION** default: ``max_log_age_days: 90``, ``max_audit_age_days: 365``
- **MASKING**  default: ``fields: ["password", "token", "secret", "api_key"]``
"""

from __future__ import annotations

from typing import TypedDict


class CompliancePolicy(TypedDict):
    policy_id: str
    policy_type: str  # "retention" | "masking"
    config: dict
    enabled: bool


_DEFAULT_RETENTION: dict = {"max_log_age_days": 90, "max_audit_age_days": 365}
_DEFAULT_MASKING: dict = {"fields": ["password", "token", "secret", "api_key"]}


_policies: dict[str, CompliancePolicy] = {}


def _default_config(policy_type: str) -> dict:
    if policy_type == "retention":
        return dict(_DEFAULT_RETENTION)
    if policy_type == "masking":
        return list(_DEFAULT_MASKING["fields"])
    return {}


def set_policy(
    policy_id: str,
    policy_type: str,
    config: dict | None = None,
    enabled: bool = True,
) -> CompliancePolicy:
    """Create or update a compliance policy.

    When *config* is omitted the built-in default for *policy_type* is used.
    """
    policy: CompliancePolicy = {
        "policy_id": policy_id,
        "policy_type": policy_type,
        "config": config if config is not None else _default_config(policy_type),
        "enabled": enabled,
    }
    _policies[policy_id] = policy
    return policy


def get_policy(policy_id: str) -> CompliancePolicy | None:
    """Retrieve a policy by id, or None."""
    return _policies.get(policy_id)


def list_policies(policy_type: str | None = None) -> list[CompliancePolicy]:
    """List all policies, optionally filtered by *policy_type*."""
    result = list(_policies.values())
    if policy_type is not None:
        result = [p for p in result if p["policy_type"] == policy_type]
    return result


def delete_policy(policy_id: str) -> bool:
    """Remove a policy.  Returns True if it existed."""
    if policy_id in _policies:
        del _policies[policy_id]
        return True
    return False


def clear_policies() -> None:
    """Remove all policies (test helper)."""
    _policies.clear()

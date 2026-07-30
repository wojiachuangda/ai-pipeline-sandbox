"""RBAC policy engine — ALLOW / DENY with wildcard matching.

Policies are stored in-memory.  Matching uses the **DENY‑priority** rule:
if any DENY policy matches the (subject, resource, action) triple the request
is **denied**; otherwise at least one ALLOW must match (default-deny).
"""

from __future__ import annotations

from typing import TypedDict


class Policy(TypedDict):
    id: str
    effect: str  # "ALLOW" | "DENY"
    subjects: list[str]
    resources: list[str]
    actions: list[str]


_policies: dict[str, Policy] = {}
_counter: int = 0


def _next_id() -> str:
    global _counter
    _counter += 1
    return f"policy-{_counter}"


def _match(pattern: str, value: str) -> bool:
    """Return True when *pattern* matches *value* (literal or ``"*"``)."""
    return pattern == "*" or pattern == value


def _policy_matches(policy: Policy, subject: str, resource: str, action: str) -> bool:
    """Check whether *policy* covers the given triple."""
    subjects_ok = any(_match(s, subject) for s in policy["subjects"])
    resources_ok = any(_match(r, resource) for r in policy["resources"])
    actions_ok = any(_match(a, action) for a in policy["actions"])
    return subjects_ok and resources_ok and actions_ok


def add_policy(
    effect: str,  # "ALLOW" | "DENY"
    subjects: list[str],
    resources: list[str],
    actions: list[str],
) -> Policy:
    """Create a new RBAC policy and return it.

    >>> add_policy("ALLOW", ["alice"], ["doc"], ["read"])
    {'id': 'policy-...', 'effect': 'ALLOW', 'subjects': ['alice'], ...}
    """
    policy: Policy = {
        "id": _next_id(),
        "effect": effect,
        "subjects": subjects,
        "resources": resources,
        "actions": actions,
    }
    _policies[policy["id"]] = policy
    return policy


def check_permission(subject: str, resource: str, action: str) -> bool:
    """Return **True** if the subject is permitted and **False** otherwise.

    DENY policies take priority.  When no DENY matches, at least one ALLOW
    must match for the request to be granted (default-deny).
    """
    denies = [p for p in _policies.values() if p["effect"] == "DENY"]
    allows = [p for p in _policies.values() if p["effect"] == "ALLOW"]

    # DENY priority
    for policy in denies:
        if _policy_matches(policy, subject, resource, action):
            return False

    # Need at least one matching ALLOW
    for policy in allows:
        if _policy_matches(policy, subject, resource, action):
            return True

    return False  # default deny


def remove_policy(policy_id: str) -> bool:
    """Remove a policy by id.  Returns True if it existed."""
    if policy_id in _policies:
        del _policies[policy_id]
        return True
    return False


def clear_policies() -> None:
    """Remove all policies (test helper)."""
    _policies.clear()
    global _counter
    _counter = 0

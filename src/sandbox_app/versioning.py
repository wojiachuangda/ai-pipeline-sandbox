"""Agent version snapshot, list, rollback, and diff.

Pure in-memory implementation — no database, no HTTP framework.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from .models import AgentVersion

# ---------------------------------------------------------------------------
# in-memory store  (keyed by agent_id → list of AgentVersion, newest first)
# ---------------------------------------------------------------------------
_versions: dict[str, list[AgentVersion]] = {}

_MAX_VERSIONS = 100


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _parse_version(ver: str) -> tuple[int, int, int]:
    major, minor, patch = ver.split(".")
    return int(major), int(minor), int(patch)


def _bump_version(current: str, *, is_major: bool = False) -> str:
    """Bump semver: major → +1.0.0, minor → +0.1.0 (patch reset)."""
    if not current:
        return "0.1.0"
    major, minor, patch = _parse_version(current)
    if is_major:
        return f"{major + 1}.0.0"
    return f"{major}.{minor + 1}.0"


def _bump_patch(current: str) -> str:
    """Bump only the PATCH segment for rollback."""
    major, minor, patch = _parse_version(current)
    return f"{major}.{minor}.{patch + 1}"


def _get_versions(agent_id: str) -> list[AgentVersion]:
    """Return version list for *agent_id* (newest-first), or empty list."""
    return _versions.get(agent_id, [])


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def create_version(
    agent_id: str,
    description: str,
    config: dict,
    *,
    is_major: bool = False,
    created_by: str = "system",
    agent_status: str = "INACTIVE",
) -> AgentVersion:
    """Snapshot the current config into a new version.

    Args:
        agent_id: Owning agent.
        description: Human-readable description of this version.
        config: Full configuration dict to snapshot.
        is_major: If True, bump the major version; otherwise bump minor.
        created_by: Who triggered this snapshot.
        agent_status: Current status of the agent (DEPRECATED agents rejected).

    Returns:
        The newly created AgentVersion.

    Raises:
        ValueError: ``VERSION_LIMIT_EXCEEDED`` or agent is ``DEPRECATED``.
    """
    if agent_status == "DEPRECATED":
        raise ValueError("VERSION_LIMIT_EXCEEDED: cannot version a DEPRECATED agent")

    versions = _get_versions(agent_id)
    if len(versions) >= _MAX_VERSIONS:
        raise ValueError("VERSION_LIMIT_EXCEEDED: agent has reached the 100-version cap")

    # Determine new semver from the current latest (which is versions[0] when sorted newest-first)
    latest_ver = versions[0].version if versions else ""
    new_ver = _bump_version(latest_ver, is_major=is_major)

    # Mark all existing versions as not current
    for v in versions:
        v.is_current = False

    version = AgentVersion(
        version_id=f"ver-{uuid.uuid4().hex[:12]}",
        agent_id=agent_id,
        version=new_ver,
        description=description,
        config=copy.deepcopy(config),
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
        is_current=True,
    )
    versions.insert(0, version)  # newest first
    _versions[agent_id] = versions
    return version


def list_versions(agent_id: str, page: int = 1, page_size: int = 20) -> dict:
    """List versions for an agent, newest first with pagination.

    Returns:
        ``{"versions": [...], "total": N}``
    """
    versions = _get_versions(agent_id)
    total = len(versions)
    start = (page - 1) * page_size
    page_items = versions[start : start + page_size]

    return {
        "versions": [
            {
                "version_id": v.version_id,
                "version": v.version,
                "description": v.description,
                "created_by": v.created_by,
                "created_at": v.created_at.isoformat(),
                "is_current": v.is_current,
            }
            for v in page_items
        ],
        "total": total,
    }


def rollback(
    agent_id: str,
    target_version_id: str,
    rollback_reason: str = "",
    *,
    agent_status: str = "INACTIVE",
) -> dict:
    """Roll back to a previous version by creating a new PATCH version with the target's config.

    Args:
        agent_id: Owning agent.
        target_version_id: The version to roll back *to*.
        rollback_reason: Why the rollback was triggered.
        agent_status: Current agent status (DEPRECATED rejected).

    Returns:
        ``{"new_version": str, "new_version_id": str, "status": "ROLLBACK_COMPLETE"}``

    Raises:
        LookupError: Target version not found.
        ValueError: Agent is DEPRECATED.
    """
    if agent_status == "DEPRECATED":
        raise ValueError("VERSION_LIMIT_EXCEEDED: cannot rollback a DEPRECATED agent")

    versions = _get_versions(agent_id)
    target = next((v for v in versions if v.version_id == target_version_id), None)
    if target is None:
        raise LookupError(f"Version {target_version_id} not found for agent {agent_id}")

    # Determine the new PATCH version from current latest
    latest_ver = versions[0].version if versions else "0.1.0"
    new_ver = _bump_patch(latest_ver)

    # Mark all existing as not current
    for v in versions:
        v.is_current = False

    version = AgentVersion(
        version_id=f"ver-{uuid.uuid4().hex[:12]}",
        agent_id=agent_id,
        version=new_ver,
        description=f"ROLLBACK to {target.version} — {rollback_reason}".rstrip(" —"),
        config=copy.deepcopy(target.config),
        created_by="rollback",
        created_at=datetime.now(timezone.utc),
        is_current=True,
    )
    versions.insert(0, version)
    _versions[agent_id] = versions

    return {
        "new_version": version.version,
        "new_version_id": version.version_id,
        "status": "ROLLBACK_COMPLETE",
    }


# ---------------------------------------------------------------------------
# diff helpers
# ---------------------------------------------------------------------------

def _diff_dicts(
    base: dict, other: dict, prefix: str = ""
) -> list[dict]:
    """Deep-compare two dicts, returning a flat list of diffs."""
    diffs: list[dict] = []
    all_keys = set(base.keys()) | set(other.keys())

    for key in sorted(all_keys):
        field_path = f"{prefix}.{key}" if prefix else key
        in_base = key in base
        in_other = key in other

        if in_base and in_other:
            bv = base[key]
            ov = other[key]
            if isinstance(bv, dict) and isinstance(ov, dict):
                diffs.extend(_diff_dicts(bv, ov, prefix=field_path))
            elif bv != ov:
                diffs.append(
                    {
                        "field_path": field_path,
                        "old_value": bv,
                        "new_value": ov,
                        "change_type": "MODIFIED",
                    }
                )
        elif in_base and not in_other:
            diffs.append(
                {
                    "field_path": field_path,
                    "old_value": base[key],
                    "new_value": None,
                    "change_type": "REMOVED",
                }
            )
        else:  # in_other, not in_base
            diffs.append(
                {
                    "field_path": field_path,
                    "old_value": None,
                    "new_value": other[key],
                    "change_type": "ADDED",
                }
            )
    return diffs


def diff_versions(agent_id: str, version_id_a: str, version_id_b: str) -> dict:
    """Compute a field-level diff between two versions' configs.

    Args:
        agent_id: Owning agent.
        version_id_a: Base version to compare from.
        version_id_b: Target version to compare to.

    Returns:
        ``{"diffs": [{"field_path", "old_value", "new_value", "change_type"}, ...]}``

    Raises:
        LookupError: Either version not found.
    """
    versions = _get_versions(agent_id)
    va = next((v for v in versions if v.version_id == version_id_a), None)
    vb = next((v for v in versions if v.version_id == version_id_b), None)

    if va is None:
        raise LookupError(f"Version {version_id_a} not found for agent {agent_id}")
    if vb is None:
        raise LookupError(f"Version {version_id_b} not found for agent {agent_id}")

    return {"diffs": _diff_dicts(va.config, vb.config)}


# ---------------------------------------------------------------------------
# testing helpers
# ---------------------------------------------------------------------------

def _reset_store() -> None:
    """Clear all stored versions (test-only)."""
    _versions.clear()

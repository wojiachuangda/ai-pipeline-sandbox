"""Multi-version traffic routing and canary configuration.

Pure in-memory implementation.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

from .models import TrafficConfig

# ---------------------------------------------------------------------------
# in-memory store  (keyed by agent_id)
# ---------------------------------------------------------------------------
_traffic_configs: dict[str, TrafficConfig] = {}

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
MAX_VERSIONS = 3


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def configure_traffic(
    agent_id: str,
    version_traffic: list[dict],
    *,
    enable_canary: bool = False,
    versions_exist: bool = True,
    agent_status: str = "ACTIVE",
) -> TrafficConfig:
    """Create or update the traffic configuration for *agent_id*.

    Args:
        agent_id: Owning agent.
        version_traffic: List of ``{"version_id": str, "weight": int}`` entries.
        enable_canary: Whether canary mode is enabled.
        versions_exist: Caller assertion that all referenced versions exist.
        agent_status: Must be ``"ACTIVE"``.

    Returns:
        The created or updated TrafficConfig.

    Raises:
        ValueError: ``TRAFFIC_WEIGHT_INVALID``, ``TOO_MANY_VERSIONS``,
                    or agent not ACTIVE.
    """
    if agent_status != "ACTIVE":
        raise ValueError("TRAFFIC_WEIGHT_INVALID: agent must be ACTIVE to configure traffic")

    if len(version_traffic) > MAX_VERSIONS:
        raise ValueError(
            f"TOO_MANY_VERSIONS: max {MAX_VERSIONS} versions allowed, got {len(version_traffic)}"
        )

    total_weight = sum(e["weight"] for e in version_traffic)
    if total_weight != 100:
        raise ValueError(
            f"TRAFFIC_WEIGHT_INVALID: weights must sum to 100, got {total_weight}"
        )

    if not version_traffic:
        raise ValueError("TRAFFIC_WEIGHT_INVALID: at least one version is required")

    if not versions_exist:
        raise LookupError("One or more referenced versions do not exist")

    config = TrafficConfig(
        config_id=f"tc-{uuid.uuid4().hex[:12]}",
        agent_id=agent_id,
        version_traffic=version_traffic,
        enable_canary=enable_canary,
        started_at=datetime.now(timezone.utc),
    )
    _traffic_configs[agent_id] = config
    return config


def get_traffic_config(agent_id: str) -> TrafficConfig | None:
    """Return the traffic config for *agent_id*, or None."""
    return _traffic_configs.get(agent_id)


def route_request(agent_id: str) -> str | None:
    """Weighted random selection of a version_id for routing.

    Returns None when no traffic config exists or all weights are zero.
    """
    config = _traffic_configs.get(agent_id)
    if config is None or not config.version_traffic:
        return None

    entries = config.version_traffic
    total = sum(e["weight"] for e in entries)
    if total == 0:
        return None

    # Weighted random selection
    r = random.uniform(0, total)
    cumulative = 0.0
    for entry in entries:
        cumulative += entry["weight"]
        if r <= cumulative:
            return entry["version_id"]

    # Fallback (shouldn't happen with correct weights)
    return entries[-1]["version_id"]


# ---------------------------------------------------------------------------
# testing helpers
# ---------------------------------------------------------------------------


def _reset_store() -> None:
    """Clear all traffic configs (test-only)."""
    _traffic_configs.clear()

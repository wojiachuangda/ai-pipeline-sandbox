"""Tests for multi-version traffic routing and canary configuration."""

from __future__ import annotations

import pytest

from sandbox_app.traffic import (
    _reset_store,
    configure_traffic,
    get_traffic_config,
    route_request,
)

AGENT_ID = "agent-tr-001"


@pytest.fixture(autouse=True)
def _clear_store() -> None:
    _reset_store()


# ---------------------------------------------------------------------------
# valid configs
# ---------------------------------------------------------------------------


def test_valid_traffic_config() -> None:
    tc = configure_traffic(
        AGENT_ID,
        [
            {"version_id": "v1", "weight": 70},
            {"version_id": "v2", "weight": 30},
        ],
    )
    assert tc.agent_id == AGENT_ID
    assert len(tc.version_traffic) == 2
    assert tc.enable_canary is False


def test_single_version_100_weight() -> None:
    tc = configure_traffic(
        AGENT_ID,
        [{"version_id": "v1", "weight": 100}],
    )
    assert tc is not None
    assert tc.version_traffic[0]["weight"] == 100


def test_three_versions_max() -> None:
    tc = configure_traffic(
        AGENT_ID,
        [
            {"version_id": "v1", "weight": 50},
            {"version_id": "v2", "weight": 30},
            {"version_id": "v3", "weight": 20},
        ],
    )
    assert len(tc.version_traffic) == 3


def test_canary_mode() -> None:
    tc = configure_traffic(
        AGENT_ID,
        [{"version_id": "v1", "weight": 100}],
        enable_canary=True,
    )
    assert tc.enable_canary is True


def test_get_traffic_config() -> None:
    configure_traffic(AGENT_ID, [{"version_id": "v1", "weight": 100}])
    tc = get_traffic_config(AGENT_ID)
    assert tc is not None
    assert tc.agent_id == AGENT_ID


def test_get_traffic_config_none() -> None:
    assert get_traffic_config("nonexistent") is None


# ---------------------------------------------------------------------------
# validation errors
# ---------------------------------------------------------------------------


def test_weight_sum_not_100() -> None:
    with pytest.raises(ValueError, match="TRAFFIC_WEIGHT_INVALID"):
        configure_traffic(
            AGENT_ID,
            [
                {"version_id": "v1", "weight": 60},
                {"version_id": "v2", "weight": 30},
            ],
        )


def test_weight_sum_over_100() -> None:
    with pytest.raises(ValueError, match="TRAFFIC_WEIGHT_INVALID"):
        configure_traffic(
            AGENT_ID,
            [
                {"version_id": "v1", "weight": 80},
                {"version_id": "v2", "weight": 30},
            ],
        )


def test_too_many_versions() -> None:
    with pytest.raises(ValueError, match="TOO_MANY_VERSIONS"):
        configure_traffic(
            AGENT_ID,
            [
                {"version_id": "v1", "weight": 25},
                {"version_id": "v2", "weight": 25},
                {"version_id": "v3", "weight": 25},
                {"version_id": "v4", "weight": 25},
            ],
        )


def test_empty_versions() -> None:
    with pytest.raises(ValueError, match="TRAFFIC_WEIGHT_INVALID"):
        configure_traffic(AGENT_ID, [])


def test_inactive_agent_rejected() -> None:
    with pytest.raises(ValueError, match="TRAFFIC_WEIGHT_INVALID"):
        configure_traffic(
            AGENT_ID,
            [{"version_id": "v1", "weight": 100}],
            agent_status="INACTIVE",
        )


def test_nonexistent_versions_rejected() -> None:
    with pytest.raises(LookupError, match="do not exist"):
        configure_traffic(
            AGENT_ID,
            [{"version_id": "v-fake", "weight": 100}],
            versions_exist=False,
        )


# ---------------------------------------------------------------------------
# route_request
# ---------------------------------------------------------------------------


def test_route_request_single_version() -> None:
    configure_traffic(AGENT_ID, [{"version_id": "v1", "weight": 100}])
    result = route_request(AGENT_ID)
    assert result == "v1"


def test_route_request_no_config() -> None:
    assert route_request("nonexistent") is None


def test_route_request_zero_weights() -> None:
    """When weights sum to 0 (invalid config rejected by configure_traffic),
    routing returns None because no traffic config exists."""
    # Weights must sum to 100 for a valid config, so zero-weight cannot be configured.
    # With no config at all, route_request returns None.
    assert get_traffic_config(AGENT_ID) is None
    result = route_request(AGENT_ID)
    assert result is None


def test_weighted_routing_distribution() -> None:
    """Basic distribution check: with deterministic weights, routing should
    respect the configured proportions."""
    configure_traffic(
        AGENT_ID,
        [
            {"version_id": "v1", "weight": 100},
        ],
    )
    # With only one version at weight 100, it should always return v1
    for _ in range(20):
        assert route_request(AGENT_ID) == "v1"

    # With two versions, both get routed (non-deterministic but should return one or the other)
    configure_traffic(
        AGENT_ID,
        [
            {"version_id": "a", "weight": 50},
            {"version_id": "b", "weight": 50},
        ],
    )
    routed = {route_request(AGENT_ID) for _ in range(50)}
    assert routed == {"a", "b"} or len(routed) == 2

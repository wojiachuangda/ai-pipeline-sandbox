"""Tests for sandbox_app.compliance — AC-6."""

import pytest

from sandbox_app.compliance import (
    clear_policies,
    delete_policy,
    get_policy,
    list_policies,
    set_policy,
)


@pytest.fixture(autouse=True)
def _clean() -> None:
    clear_policies()


class TestRetentionPolicy:
    def test_set_and_get_retention(self) -> None:
        """AC-6.1: set a RETENTION policy and read it back."""
        config = {"max_log_age_days": 30, "max_audit_age_days": 180}
        p = set_policy("ret-1", "retention", config)
        assert p["policy_id"] == "ret-1"
        assert p["policy_type"] == "retention"
        assert p["enabled"] is True

        got = get_policy("ret-1")
        assert got is not None
        assert got["config"] == config

    def test_default_retention_config(self) -> None:
        """Set a RETENTION policy without config uses defaults."""
        p = set_policy("def-ret", "retention")
        assert p["config"]["max_log_age_days"] == 90
        assert p["config"]["max_audit_age_days"] == 365


class TestMaskingPolicy:
    def test_set_and_get_masking(self) -> None:
        """AC-6.2: set a MASKING policy and read it back."""
        config = {"fields": ["password", "ssn"]}
        p = set_policy("mask-1", "masking", config)
        assert p["policy_type"] == "masking"

        got = get_policy("mask-1")
        assert got is not None
        assert got["config"] == config

    def test_default_masking_config(self) -> None:
        """Set a MASKING policy without config uses defaults."""
        p = set_policy("def-mask", "masking")
        assert p["config"] == ["password", "token", "secret", "api_key"]


class TestListPolicies:
    def test_list_all(self) -> None:
        """AC-6.3: list all policies across types."""
        set_policy("a", "retention")
        set_policy("b", "masking")
        all_p = list_policies()
        assert len(all_p) == 2

    def test_filter_by_type(self) -> None:
        """AC-6.4: filter by policy_type."""
        set_policy("a", "retention")
        set_policy("b", "masking")
        masks = list_policies("masking")
        assert len(masks) == 1
        assert masks[0]["policy_id"] == "b"

    def test_filter_nonexistent_type(self) -> None:
        set_policy("a", "retention")
        assert list_policies("unknown") == []


class TestDeletePolicy:
    def test_delete_existing(self) -> None:
        """AC-6.5: delete removes the policy."""
        set_policy("x", "retention")
        assert delete_policy("x") is True
        assert get_policy("x") is None

    def test_delete_nonexistent(self) -> None:
        assert delete_policy("nope") is False


class TestOverwrite:
    def test_overwrite_existing_policy(self) -> None:
        """AC-6.6: setting a policy with an existing id overwrites."""
        set_policy("same-id", "retention", {"max_log_age_days": 10})
        set_policy("same-id", "retention", {"max_log_age_days": 50})
        got = get_policy("same-id")
        assert got is not None
        assert got["config"]["max_log_age_days"] == 50

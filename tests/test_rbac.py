"""Tests for sandbox_app.rbac — AC-7."""

import pytest

from sandbox_app.rbac import add_policy, check_permission, clear_policies, remove_policy


@pytest.fixture(autouse=True)
def _clean() -> None:
    """Ensure each test starts with a clean policy store."""
    clear_policies()


class TestExactAllow:
    def test_exact_match_allow(self) -> None:
        """AC-7.1: exact subject/resource/action ALLOW match → True."""
        add_policy("ALLOW", ["alice"], ["doc"], ["read"])
        assert check_permission("alice", "doc", "read") is True

    def test_exact_mismatch(self) -> None:
        """A non-matching triple is denied."""
        add_policy("ALLOW", ["alice"], ["doc"], ["read"])
        assert check_permission("bob", "doc", "read") is False


class TestWildcard:
    def test_wildcard_subject(self) -> None:
        """AC-7.2: '*' in subjects matches any subject."""
        add_policy("ALLOW", ["*"], ["doc"], ["read"])
        assert check_permission("anyone", "doc", "read") is True

    def test_wildcard_resource(self) -> None:
        add_policy("ALLOW", ["alice"], ["*"], ["read"])
        assert check_permission("alice", "any-resource", "read") is True

    def test_wildcard_action(self) -> None:
        add_policy("ALLOW", ["alice"], ["doc"], ["*"])
        assert check_permission("alice", "doc", "write") is True

    def test_full_wildcard(self) -> None:
        add_policy("ALLOW", ["*"], ["*"], ["*"])
        assert check_permission("random", "thing", "action") is True


class TestDefaultDeny:
    def test_default_deny(self) -> None:
        """AC-7.3: no matching policy → False (default-deny)."""
        assert check_permission("alice", "doc", "read") is False


class TestDenyPriority:
    def test_deny_overrides_allow(self) -> None:
        """AC-7.4: DENY takes priority over ALLOW."""
        add_policy("ALLOW", ["alice"], ["doc"], ["read"])
        add_policy("DENY", ["alice"], ["doc"], ["read"])
        assert check_permission("alice", "doc", "read") is False

    def test_deny_wildcard_overrides_allow(self) -> None:
        """Wildcard DENY still overrides a specific ALLOW."""
        add_policy("ALLOW", ["alice"], ["doc"], ["read"])
        add_policy("DENY", ["*"], ["doc"], ["read"])
        assert check_permission("alice", "doc", "read") is False


class TestMultipleSubjects:
    def test_match_one_of_many_subjects(self) -> None:
        """AC-7.5: a policy with multiple subjects matches if any matches."""
        add_policy("ALLOW", ["alice", "bob", "charlie"], ["doc"], ["read"])
        assert check_permission("bob", "doc", "read") is True

    def test_match_one_of_many_resources(self) -> None:
        add_policy("ALLOW", ["alice"], ["doc", "wiki"], ["read"])
        assert check_permission("alice", "wiki", "read") is True


class TestRemovePolicy:
    def test_remove_policy_affects_check(self) -> None:
        """AC-7.6: removing a policy changes permission outcome."""
        policy = add_policy("ALLOW", ["alice"], ["doc"], ["read"])
        assert check_permission("alice", "doc", "read") is True
        removed = remove_policy(policy["id"])
        assert removed is True
        assert check_permission("alice", "doc", "read") is False

    def test_remove_nonexistent(self) -> None:
        assert remove_policy("nonexistent") is False

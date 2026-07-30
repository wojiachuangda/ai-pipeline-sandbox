"""Tests for agent versioning: create, list, rollback, diff."""

from __future__ import annotations

import pytest

from sandbox_app.versioning import (
    _reset_store,
    create_version,
    diff_versions,
    list_versions,
    rollback,
)

AGENT_ID = "agent-001"


@pytest.fixture(autouse=True)
def _clear_store() -> None:
    _reset_store()


# ---------------------------------------------------------------------------
# create_version
# ---------------------------------------------------------------------------


def test_create_version_initial() -> None:
    v = create_version(AGENT_ID, "initial", {"model": "gpt-4"})
    assert v.version == "0.1.0"
    assert v.is_current is True
    assert v.config == {"model": "gpt-4"}


def test_create_version_minor_bump() -> None:
    create_version(AGENT_ID, "first", {})
    v2 = create_version(AGENT_ID, "second", {}, is_major=False)
    assert v2.version == "0.2.0"
    assert v2.is_current is True


def test_create_version_major_bump() -> None:
    create_version(AGENT_ID, "first", {})
    v2 = create_version(AGENT_ID, "second", {}, is_major=True)
    assert v2.version == "1.0.0"


def test_only_one_is_current() -> None:
    v1 = create_version(AGENT_ID, "v1", {})
    v2 = create_version(AGENT_ID, "v2", {})
    v3 = create_version(AGENT_ID, "v3", {})

    assert v1.is_current is False
    assert v2.is_current is False
    assert v3.is_current is True


def test_version_limit() -> None:
    # 100 versions should succeed
    for i in range(100):
        create_version(AGENT_ID, f"v{i}", {"i": i})
    # 101st should fail
    with pytest.raises(ValueError, match="VERSION_LIMIT_EXCEEDED"):
        create_version(AGENT_ID, "overflow", {})


def test_deprecated_agent_cannot_version() -> None:
    with pytest.raises(ValueError, match="VERSION_LIMIT_EXCEEDED"):
        create_version(AGENT_ID, "should fail", {}, agent_status="DEPRECATED")


# ---------------------------------------------------------------------------
# list_versions
# ---------------------------------------------------------------------------


def test_list_versions_descending() -> None:
    create_version(AGENT_ID, "first", {"n": 1})
    create_version(AGENT_ID, "second", {"n": 2})
    create_version(AGENT_ID, "third", {"n": 3})

    result = list_versions(AGENT_ID)
    assert result["total"] == 3
    versions = result["versions"]
    # newest first
    assert [v["description"] for v in versions] == ["third", "second", "first"]


def test_list_versions_is_current_field() -> None:
    create_version(AGENT_ID, "old", {})
    create_version(AGENT_ID, "new one", {})

    result = list_versions(AGENT_ID)
    current_count = sum(1 for v in result["versions"] if v["is_current"])
    assert current_count == 1


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------


def test_rollback_creates_patch() -> None:
    v1 = create_version(AGENT_ID, "v0.1.0", {"model": "a"})
    create_version(AGENT_ID, "v0.2.0", {"model": "b"})

    result = rollback(AGENT_ID, v1.version_id, "bad config")
    assert result["status"] == "ROLLBACK_COMPLETE"

    # new version should be a PATCH bump from latest (0.2.0 → 0.2.1)
    assert result["new_version"] == "0.2.1"

    # the new version should have v1's config
    versions = list_versions(AGENT_ID)["versions"]
    assert versions[0]["version"] == "0.2.1"
    assert versions[0]["is_current"] is True


def test_rollback_nonexistent_target() -> None:
    create_version(AGENT_ID, "v0.1.0", {})
    with pytest.raises(LookupError, match="not found"):
        rollback(AGENT_ID, "nonexistent-id")


def test_rollback_deprecated_agent_rejected() -> None:
    create_version(AGENT_ID, "v0.1.0", {})
    with pytest.raises(ValueError, match="VERSION_LIMIT_EXCEEDED"):
        rollback(AGENT_ID, "any-id", agent_status="DEPRECATED")


# ---------------------------------------------------------------------------
# diff_versions
# ---------------------------------------------------------------------------


def test_diff_added_modified_removed() -> None:
    v1 = create_version(AGENT_ID, "base", {"a": 1, "b": 2, "nested": {"x": "old"}})
    v2 = create_version(AGENT_ID, "changed", {"a": 1, "b": 99, "c": 3, "nested": {"x": "new"}})

    result = diff_versions(AGENT_ID, v1.version_id, v2.version_id)
    diffs = {d["field_path"]: d for d in result["diffs"]}

    assert diffs["b"]["change_type"] == "MODIFIED"
    assert diffs["b"]["old_value"] == 2
    assert diffs["b"]["new_value"] == 99

    assert diffs["c"]["change_type"] == "ADDED"
    assert diffs["c"]["old_value"] is None
    assert diffs["c"]["new_value"] == 3

    assert diffs["nested.x"]["change_type"] == "MODIFIED"
    assert diffs["nested.x"]["old_value"] == "old"
    assert diffs["nested.x"]["new_value"] == "new"


def test_diff_removed_key() -> None:
    v1 = create_version(AGENT_ID, "v1", {"x": 1, "y": 2})
    v2 = create_version(AGENT_ID, "v2", {"x": 1})

    result = diff_versions(AGENT_ID, v1.version_id, v2.version_id)
    diffs = {d["field_path"]: d for d in result["diffs"]}

    assert diffs["y"]["change_type"] == "REMOVED"
    assert diffs["y"]["old_value"] == 2
    assert diffs["y"]["new_value"] is None


def test_diff_nonexistent_version() -> None:
    v1 = create_version(AGENT_ID, "v1", {})
    with pytest.raises(LookupError, match="not found"):
        diff_versions(AGENT_ID, v1.version_id, "nonexistent")
    with pytest.raises(LookupError, match="not found"):
        diff_versions(AGENT_ID, "nonexistent", v1.version_id)


def test_diff_no_changes() -> None:
    v1 = create_version(AGENT_ID, "v1", {"a": 1})
    v2 = create_version(AGENT_ID, "v2", {"a": 1})

    result = diff_versions(AGENT_ID, v1.version_id, v2.version_id)
    assert result["diffs"] == []

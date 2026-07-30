"""Tests for lifecycle state machine and history tracking (AC-3, AC-4)."""

import uuid

import pytest

from sandbox_app.domain import (
    TaskLifecycleStatus,
    StatusTransition,
    InvalidTransitionError,
)
from sandbox_app.lifecycle import LifecycleManager


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def lifecycle() -> LifecycleManager:
    return LifecycleManager()


@pytest.fixture
def execution_id() -> uuid.UUID:
    return uuid.uuid4()


# ── AC-3: Full lifecycle transitions ────────────────────────────────────────


def test_full_lifecycle_transitions(lifecycle: LifecycleManager, execution_id: uuid.UUID) -> None:
    """AC-3: PENDING → QUEUED → ASSIGNED → RUNNING → SUCCEEDED all succeed."""
    # Seed initial status
    lifecycle.set_initial_status(execution_id, TaskLifecycleStatus.PENDING)

    # Walk through the happy path
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.PENDING, TaskLifecycleStatus.QUEUED, "enqueuer"
    )
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.QUEUED, TaskLifecycleStatus.ASSIGNED, "scheduler"
    )
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.ASSIGNED, TaskLifecycleStatus.RUNNING, "runner"
    )
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.RUNNING, TaskLifecycleStatus.SUCCEEDED, "runner"
    )

    timeline = lifecycle.get_timeline(execution_id)
    # PENDING (set_initial) + 4 transitions = 5 entries
    assert len(timeline) == 5
    statuses = [t.status for t in timeline]
    assert statuses == [
        TaskLifecycleStatus.PENDING,
        TaskLifecycleStatus.QUEUED,
        TaskLifecycleStatus.ASSIGNED,
        TaskLifecycleStatus.RUNNING,
        TaskLifecycleStatus.SUCCEEDED,
    ]


def test_status_history_timestamps(lifecycle: LifecycleManager, execution_id: uuid.UUID) -> None:
    """AC-4: each transition records timestamp, actor, and detail."""
    lifecycle.set_initial_status(execution_id, TaskLifecycleStatus.PENDING)

    transition = lifecycle.record_transition(
        execution_id,
        from_status=TaskLifecycleStatus.PENDING,
        to_status=TaskLifecycleStatus.QUEUED,
        actor="test_actor",
        detail="Test transition",
    )

    assert isinstance(transition.timestamp, type(transition.timestamp))
    assert transition.actor == "test_actor"
    assert transition.detail == "Test transition"
    assert transition.status == TaskLifecycleStatus.QUEUED


def test_invalid_transition_blocked(lifecycle: LifecycleManager, execution_id: uuid.UUID) -> None:
    """AC-3: jumping from PENDING → RUNNING is rejected."""
    lifecycle.set_initial_status(execution_id, TaskLifecycleStatus.PENDING)

    with pytest.raises(InvalidTransitionError) as exc_info:
        lifecycle.record_transition(
            execution_id,
            from_status=TaskLifecycleStatus.PENDING,
            to_status=TaskLifecycleStatus.RUNNING,
        )
    assert "PENDING" in str(exc_info.value)
    assert "RUNNING" in str(exc_info.value)


def test_cancelled_terminal(lifecycle: LifecycleManager, execution_id: uuid.UUID) -> None:
    """AC-3: once CANCELLED, no further transitions are allowed."""
    lifecycle.set_initial_status(execution_id, TaskLifecycleStatus.PENDING)
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.PENDING, TaskLifecycleStatus.CANCELLED, "user"
    )

    with pytest.raises(InvalidTransitionError):
        lifecycle.record_transition(
            execution_id, TaskLifecycleStatus.CANCELLED, TaskLifecycleStatus.QUEUED, "retry"
        )


def test_succeeded_terminal(lifecycle: LifecycleManager, execution_id: uuid.UUID) -> None:
    """AC-3: SUCCEEDED is a terminal state."""
    lifecycle.set_initial_status(execution_id, TaskLifecycleStatus.PENDING)
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.PENDING, TaskLifecycleStatus.QUEUED
    )
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.QUEUED, TaskLifecycleStatus.ASSIGNED
    )
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.ASSIGNED, TaskLifecycleStatus.RUNNING
    )
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.RUNNING, TaskLifecycleStatus.SUCCEEDED
    )

    with pytest.raises(InvalidTransitionError):
        lifecycle.record_transition(
            execution_id, TaskLifecycleStatus.SUCCEEDED, TaskLifecycleStatus.RUNNING
        )


def test_failed_terminal(lifecycle: LifecycleManager, execution_id: uuid.UUID) -> None:
    """AC-3: FAILED is a terminal state."""
    lifecycle.set_initial_status(execution_id, TaskLifecycleStatus.PENDING)
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.PENDING, TaskLifecycleStatus.QUEUED
    )
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.QUEUED, TaskLifecycleStatus.ASSIGNED
    )
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.ASSIGNED, TaskLifecycleStatus.RUNNING
    )
    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.RUNNING, TaskLifecycleStatus.FAILED
    )

    with pytest.raises(InvalidTransitionError):
        lifecycle.record_transition(
            execution_id, TaskLifecycleStatus.FAILED, TaskLifecycleStatus.RUNNING
        )


def test_timeline_queryable(lifecycle: LifecycleManager, execution_id: uuid.UUID) -> None:
    """AC-3: get_timeline returns the full history in order."""
    lifecycle.set_initial_status(execution_id, TaskLifecycleStatus.PENDING)

    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.PENDING, TaskLifecycleStatus.QUEUED
    )
    timeline = lifecycle.get_timeline(execution_id)
    assert len(timeline) == 2

    # StatusHistoryTransition model
    for t in timeline:
        assert isinstance(t, StatusTransition)


def test_timeline_404_for_unknown(lifecycle: LifecycleManager) -> None:
    """AC-3: unknown execution_id has empty timeline, not None."""
    unknown = uuid.uuid4()
    timeline = lifecycle.get_timeline(unknown)
    assert timeline == []
    assert lifecycle.get_current_status(unknown) is None


def test_get_current_status(lifecycle: LifecycleManager, execution_id: uuid.UUID) -> None:
    """AC-3: get_current_status returns the latest status."""
    lifecycle.set_initial_status(execution_id, TaskLifecycleStatus.PENDING)
    assert lifecycle.get_current_status(execution_id) == TaskLifecycleStatus.PENDING

    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.PENDING, TaskLifecycleStatus.QUEUED
    )
    assert lifecycle.get_current_status(execution_id) == TaskLifecycleStatus.QUEUED


def test_compute_duration_ms(lifecycle: LifecycleManager, execution_id: uuid.UUID) -> None:
    """AC-3: compute_duration_ms returns the elapsed time between first and last transition."""
    lifecycle.set_initial_status(execution_id, TaskLifecycleStatus.PENDING)
    assert lifecycle.compute_duration_ms(execution_id) is None  # only 1 entry

    lifecycle.record_transition(
        execution_id, TaskLifecycleStatus.PENDING, TaskLifecycleStatus.QUEUED
    )
    duration = lifecycle.compute_duration_ms(execution_id)
    assert duration is not None
    assert duration >= 0


def test_entry_exists(lifecycle: LifecycleManager, execution_id: uuid.UUID) -> None:
    """entry_exists returns True only for known execution_ids."""
    assert not lifecycle.entry_exists(execution_id)
    lifecycle.set_initial_status(execution_id, TaskLifecycleStatus.PENDING)
    assert lifecycle.entry_exists(execution_id)

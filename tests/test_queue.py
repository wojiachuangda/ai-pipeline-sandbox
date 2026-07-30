"""Tests for task queue engine (AC-1, AC-2, AC-5)."""

import uuid

import pytest

from sandbox_app.domain import (
    SchedulingPolicy,
    QueueFullError,
    DuplicateEnqueueError,
)
from sandbox_app.queue import TaskQueue
from sandbox_app import TaskLifecycleStatus


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def queue() -> TaskQueue:
    return TaskQueue(max_size=10000)


@pytest.fixture
def small_queue() -> TaskQueue:
    return TaskQueue(max_size=3)


# ── AC-1: Enqueue API — entry_id / position / dedup ─────────────────────────


def test_enqueue_returns_entry_id_and_position(queue: TaskQueue) -> None:
    """AC-1: enqueue returns a valid queue_entry_id and position."""
    task_id = uuid.uuid4()
    resp = queue.enqueue(task_id, priority=5)

    assert isinstance(resp.queue_entry_id, uuid.UUID)
    assert resp.position == 1


def test_duplicate_enqueue_prevented(queue: TaskQueue) -> None:
    """AC-1: enqueuing the same task_id twice raises DuplicateEnqueueError."""
    task_id = uuid.uuid4()
    queue.enqueue(task_id, priority=5)

    with pytest.raises(DuplicateEnqueueError) as exc_info:
        queue.enqueue(task_id, priority=3)
    assert exc_info.value.task_id == task_id


def test_enqueue_position_increments(queue: TaskQueue) -> None:
    """AC-1: position increments as tasks are added."""
    ids = [uuid.uuid4() for _ in range(5)]
    for idx, task_id in enumerate(ids, start=1):
        resp = queue.enqueue(task_id)
        assert resp.position == idx


def test_get_entry_by_entry_id(queue: TaskQueue) -> None:
    """AC-1: get_entry returns the correct QueueEntry by queue_entry_id."""
    task_id = uuid.uuid4()
    resp = queue.enqueue(task_id, priority=7)
    entry = queue.get_entry(resp.queue_entry_id)
    assert entry is not None
    assert entry.task_id == task_id
    assert entry.priority == 7


def test_get_position(queue: TaskQueue) -> None:
    """AC-1: get_position returns correct 1-based position."""
    t1, t2, t3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    queue.enqueue(t1, priority=5)
    queue.enqueue(t2, priority=7)  # higher priority → position 1
    queue.enqueue(t3, priority=5)

    assert queue.get_position(t2) == 1  # highest priority
    assert queue.get_position(t1) == 2  # same priority, earlier FIFO
    assert queue.get_position(t3) == 3


def test_get_position_none_for_unknown(queue: TaskQueue) -> None:
    """AC-1: get_position returns None for an unknown task_id."""
    assert queue.get_position(uuid.uuid4()) is None


# ── AC-2: Dequeue / scheduling ──────────────────────────────────────────────


def test_priority_first_ordering(queue: TaskQueue) -> None:
    """AC-2: highest-priority tasks are dequeued first."""
    t_low = uuid.uuid4()
    t_med = uuid.uuid4()
    t_high = uuid.uuid4()

    queue.enqueue(t_low, priority=1)
    queue.enqueue(t_med, priority=5)
    queue.enqueue(t_high, priority=9)

    first = queue.dequeue()
    assert first.task_id == t_high

    second = queue.dequeue()
    assert second.task_id == t_med

    third = queue.dequeue()
    assert third.task_id == t_low


def test_fifo_within_same_priority(queue: TaskQueue) -> None:
    """AC-2: tasks with the same priority are dequeued FIFO."""
    t1, t2, t3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    queue.enqueue(t1, priority=5)
    queue.enqueue(t2, priority=5)
    queue.enqueue(t3, priority=5)

    assert queue.dequeue().task_id == t1
    assert queue.dequeue().task_id == t2
    assert queue.dequeue().task_id == t3


def test_round_robin_policy(queue: TaskQueue) -> None:
    """AC-2: ROUND_ROBIN cycles through priority groups."""
    # Priority 1: t1
    # Priority 3: t3a, t3b
    # Priority 5: t5
    t1 = uuid.uuid4()
    t5 = uuid.uuid4()
    t3a = uuid.uuid4()
    t3b = uuid.uuid4()

    queue.enqueue(t1, priority=1)
    queue.enqueue(t5, priority=5)
    queue.enqueue(t3a, priority=3)
    queue.enqueue(t3b, priority=3)

    # Round-robin: cycle through keys [1, 3, 5] → first: p1 → t1
    first = queue.dequeue(policy=SchedulingPolicy.ROUND_ROBIN)
    assert first.task_id == t1

    # Next: p3 → t3a
    second = queue.dequeue(policy=SchedulingPolicy.ROUND_ROBIN)
    assert second.task_id == t3a

    # Next: p5 → t5
    third = queue.dequeue(policy=SchedulingPolicy.ROUND_ROBIN)
    assert third.task_id == t5

    # Next: p3 → t3b
    fourth = queue.dequeue(policy=SchedulingPolicy.ROUND_ROBIN)
    assert fourth.task_id == t3b


def test_dequeue_updates_status(queue: TaskQueue) -> None:
    """AC-2: dequeued entry status is ASSIGNED."""
    task_id = uuid.uuid4()
    queue.enqueue(task_id, priority=0)
    entry = queue.dequeue()
    assert entry.status == TaskLifecycleStatus.ASSIGNED


def test_dequeue_empty_raises_index_error(queue: TaskQueue) -> None:
    """AC-2: dequeuing from empty queue raises IndexError."""
    with pytest.raises(IndexError, match="Queue is empty"):
        queue.dequeue()


def test_cancel_removes_from_queue(queue: TaskQueue) -> None:
    """AC-3: cancel removes the task from the queue and transitions to CANCELLED."""
    task_id = uuid.uuid4()
    queue.enqueue(task_id, priority=5)
    assert queue.size == 1

    queue.cancel(task_id)
    assert queue.size == 0
    assert queue.get_position(task_id) is None


def test_cancel_unknown_raises_key_error(queue: TaskQueue) -> None:
    """Cancel on unknown task_id raises KeyError."""
    with pytest.raises(KeyError):
        queue.cancel(uuid.uuid4())


# ── AC-5: QUEUE_FULL ────────────────────────────────────────────────────────


def test_queue_full_raises(small_queue: TaskQueue) -> None:
    """AC-5: enqueuing beyond max_size raises QueueFullError."""
    for _ in range(3):
        small_queue.enqueue(uuid.uuid4())

    with pytest.raises(QueueFullError) as exc_info:
        small_queue.enqueue(uuid.uuid4())
    assert exc_info.value.max_size == 3


def test_queue_full_error_code(small_queue: TaskQueue) -> None:
    """AC-5: QueueFullError carries max_size for the HTTP 429 handler."""
    for _ in range(3):
        small_queue.enqueue(uuid.uuid4())

    with pytest.raises(QueueFullError) as exc_info:
        small_queue.enqueue(uuid.uuid4())
    # The API handler maps this to 429 with error_code QUEUE_FULL
    assert exc_info.value.max_size == 3
    assert "Queue is full" in str(exc_info.value)

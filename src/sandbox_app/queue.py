"""Task queue engine — enqueue, dequeue, position query, and scheduling policies (AC-1, AC-2, AC-5)."""

from __future__ import annotations

import heapq
import itertools
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from .domain import (
    TaskLifecycleStatus,
    SchedulingPolicy,
    QueueEntry,
    EnqueueResponse,
    QueueFullError,
    DuplicateEnqueueError,
)
from .lifecycle import LifecycleManager


# ── Internal ──────────────────────────────────────────────────────────────

_ENQUEUE_COUNTER = itertools.count()


def _next_order() -> int:
    """Monotonically-increasing counter for FIFO tie-breaking."""
    return next(_ENQUEUE_COUNTER)


# ── Queue Engine ─────────────────────────────────────────────────────────


class TaskQueue:
    """In-memory priority queue with pluggable scheduling policies."""

    def __init__(
        self,
        max_size: int = 10000,
        policy: SchedulingPolicy = SchedulingPolicy.PRIORITY_FIRST,
        lifecycle: LifecycleManager | None = None,
    ) -> None:
        self._max_size = max_size
        self._policy = policy
        self._lifecycle = lifecycle or LifecycleManager()

        # Internal state
        self._heap: list[tuple[int, int, QueueEntry]] = []  # (-priority, order, entry)
        self._by_task_id: dict[uuid.UUID, QueueEntry] = {}   # task_id → entry
        self._by_entry_id: dict[uuid.UUID, QueueEntry] = {}  # queue_entry_id → entry
        self._dequeued: set[uuid.UUID] = set()               # removed entry ids

        # Round-robin state
        self._rr_groups: dict[int, list[QueueEntry]] = defaultdict(list)
        self._rr_cycle: itertools.cycle | None = None
        self._rr_keys: list[int] = []

    # ── properties ───────────────────────────────────────────────────────

    @property
    def lifecycle(self) -> LifecycleManager:
        """The lifecycle manager backing this queue."""
        return self._lifecycle

    @property
    def size(self) -> int:
        """Number of entries currently waiting in the queue."""
        return len(self._heap)

    @property
    def max_size(self) -> int:
        return self._max_size

    # ── enqueue / dequeue ────────────────────────────────────────────────

    def enqueue(
        self,
        task_id: uuid.UUID,
        priority: int = 0,
        execution_params: dict | None = None,
    ) -> EnqueueResponse:
        """Add a task to the queue (AC-1).  Raises :exc:`DuplicateEnqueueError`
        when *task_id* is already present, or :exc:`QueueFullError` when the
        queue is at capacity (AC-5)."""
        # Duplicate check
        if task_id in self._by_task_id:
            existing = self._by_task_id[task_id]
            raise DuplicateEnqueueError(task_id, existing.queue_entry_id)

        # Capacity check
        if self._heap is not None and len(self._heap) >= self._max_size:
            raise QueueFullError(self._max_size, task_id)

        entry = QueueEntry(
            queue_entry_id=uuid.uuid4(),
            task_id=task_id,
            priority=priority,
            position=-1,  # computed below
            status=TaskLifecycleStatus.QUEUED,
            enqueued_at=datetime.now(timezone.utc),
            execution_params=execution_params or {},
        )

        # Track lifecycle
        self._lifecycle.set_initial_status(entry.queue_entry_id, TaskLifecycleStatus.PENDING)
        self._lifecycle.record_transition(
            entry.queue_entry_id,
            from_status=TaskLifecycleStatus.PENDING,
            to_status=TaskLifecycleStatus.QUEUED,
            actor="system",
            detail="Enqueued",
        )

        # Push to heap: (-priority, order, entry) → heapq is min-heap by default
        order = _next_order()
        heapq.heappush(self._heap, (-priority, order, entry))
        self._by_task_id[task_id] = entry
        self._by_entry_id[entry.queue_entry_id] = entry

        # Also maintain round-robin substructure
        self._rr_groups[priority].append(entry)
        if priority not in self._rr_keys:
            self._rr_keys = sorted(self._rr_groups.keys())
            self._rr_cycle = itertools.cycle(self._rr_keys) if self._rr_keys else None

        # Compute position
        position = self.get_position(task_id)

        return EnqueueResponse(
            queue_entry_id=entry.queue_entry_id,
            position=position,
            estimated_start_time=None,
        )

    def dequeue(
        self,
        policy: SchedulingPolicy | None = None,
    ) -> QueueEntry:
        """Pop the next task according to *policy* (AC-2).

        If *policy* is omitted the queue's default policy is used.
        Returns the dequeued entry with status set to ``ASSIGNED``.
        Raises :exc:`IndexError` when the queue is empty.
        """
        effective_policy = policy or self._policy

        if effective_policy == SchedulingPolicy.ROUND_ROBIN:
            entry = self._dequeue_round_robin()
        else:
            # Default: PRIORITY_FIRST (and placeholder fallback for unimplemented)
            entry = self._dequeue_priority_first()

        # Clean up indexes
        self._by_task_id.pop(entry.task_id, None)
        self._by_entry_id.pop(entry.queue_entry_id, None)
        self._dequeued.add(entry.queue_entry_id)

        # Remove from round-robin groups
        self._remove_from_rr_group(entry)

        # Update lifecycle
        self._lifecycle.record_transition(
            entry.queue_entry_id,
            from_status=TaskLifecycleStatus.QUEUED,
            to_status=TaskLifecycleStatus.ASSIGNED,
            actor="system",
            detail="Dequeued for assignment",
        )

        entry.status = TaskLifecycleStatus.ASSIGNED
        return entry

    def _dequeue_priority_first(self) -> QueueEntry:
        """Highest priority (largest number) first; FIFO within same priority."""
        if not self._heap:
            raise IndexError("Queue is empty")
        neg_prio, order, entry = heapq.heappop(self._heap)
        return entry

    def _dequeue_round_robin(self) -> QueueEntry:
        """Cycle through priority groups, taking one from each group per turn."""
        if not self._heap:
            raise IndexError("Queue is empty")

        # Get current non-empty groups sorted by priority
        keys = sorted(k for k, v in self._rr_groups.items() if v)
        if not keys:
            raise IndexError("Queue is empty (no non-empty round-robin groups)")

        # Use persistent cycle, advancing until we hit a non-empty group
        if self._rr_cycle is None:
            self._rr_keys = keys
            self._rr_cycle = itertools.cycle(keys)

        # Advance through the cycle to find a non-empty group
        for _ in range(len(keys) + 1):
            key = next(self._rr_cycle)
            group = self._rr_groups.get(key)
            if group:
                entry = group.pop(0)
                # Also remove from main heap
                self._heap = [
                    item for item in self._heap if item[2].queue_entry_id != entry.queue_entry_id
                ]
                heapq.heapify(self._heap)
                # Refresh keys if this group is now empty
                if not group:
                    self._rr_groups.pop(key, None)
                    self._rr_keys = sorted(self._rr_groups.keys())
                    self._rr_cycle = itertools.cycle(self._rr_keys) if self._rr_keys else None
                return entry

        raise IndexError("Queue is empty")

    def _remove_from_rr_group(self, entry: QueueEntry) -> None:
        """Remove *entry* from its round-robin group."""
        group = self._rr_groups.get(entry.priority, [])
        self._rr_groups[entry.priority] = [e for e in group if e.queue_entry_id != entry.queue_entry_id]
        if not self._rr_groups[entry.priority]:
            self._rr_groups.pop(entry.priority, None)
            self._rr_keys = sorted(self._rr_groups.keys())

    # ── query ────────────────────────────────────────────────────────────

    def get_entry(self, entry_id: uuid.UUID) -> QueueEntry | None:
        """Look up a queue entry by its *entry_id*."""
        return self._by_entry_id.get(entry_id)

    def get_entry_by_task_id(self, task_id: uuid.UUID) -> QueueEntry | None:
        """Look up a queue entry by the business *task_id*."""
        return self._by_task_id.get(task_id)

    def get_entry_by_id(self, identifier: uuid.UUID) -> QueueEntry | None:
        """Try *identifier* as entry_id first, then as task_id."""
        return self._by_entry_id.get(identifier) or self._by_task_id.get(identifier)

    def get_position(self, task_id: uuid.UUID) -> int | None:
        """Return the 1-based position of *task_id* in the queue, or *None*."""
        entry = self._by_task_id.get(task_id)
        if entry is None:
            return None

        # Sort heap entries: (-priority, order) → highest priority first, then FIFO
        sorted_entries = sorted(self._heap, key=lambda x: (x[0], x[1]))
        for idx, item in enumerate(sorted_entries, start=1):
            if item[2].task_id == task_id:
                return idx
        return None

    def cancel(self, task_id: uuid.UUID) -> None:
        """Remove *task_id* from the queue and transition to CANCELLED (AC-3).

        Raises :exc:`KeyError` when *task_id* is not found.
        """
        entry = self._by_task_id.get(task_id)
        if entry is None:
            raise KeyError(f"Task {task_id} not found in queue")

        # Remove from heap
        self._heap = [item for item in self._heap if item[2].task_id != task_id]
        heapq.heapify(self._heap)

        # Clean indexes
        self._by_task_id.pop(task_id, None)
        self._by_entry_id.pop(entry.queue_entry_id, None)
        self._remove_from_rr_group(entry)

        # Lifecycle transition
        current = self._lifecycle.get_current_status(entry.queue_entry_id)
        if current:
            self._lifecycle.record_transition(
                entry.queue_entry_id,
                from_status=current,
                to_status=TaskLifecycleStatus.CANCELLED,
                actor="system",
                detail="Cancelled from queue",
            )

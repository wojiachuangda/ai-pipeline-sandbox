"""Lifecycle state machine and history tracking (AC-3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .domain import (
    TaskLifecycleStatus,
    StatusTransition,
    InvalidTransitionError,
    VALID_TRANSITIONS,
)


class LifecycleManager:
    """Manages task lifecycle transitions and maintains an in-memory history.

    Each tracked execution gets a history of ``StatusTransition`` records.
    """

    def __init__(self, retention_days: int = 90) -> None:
        self._retention_days = retention_days
        self._histories: dict[uuid.UUID, list[StatusTransition]] = {}

    # ── helpers ──────────────────────────────────────────────────────────

    def _ensure_tracked(self, execution_id: uuid.UUID) -> None:
        """Create a bare entry if the execution isn't tracked yet."""
        if execution_id not in self._histories:
            self._histories[execution_id] = []

    # ── public API ───────────────────────────────────────────────────────

    def record_transition(
        self,
        execution_id: uuid.UUID,
        from_status: TaskLifecycleStatus,
        to_status: TaskLifecycleStatus,
        actor: str = "system",
        detail: str = "",
    ) -> StatusTransition:
        """Validate and record a state transition.  Raises
        :class:`InvalidTransitionError` when the move is disallowed."""
        self._ensure_tracked(execution_id)

        self.validate_transition(from_status, to_status)

        transition = StatusTransition(
            status=to_status,
            timestamp=datetime.now(timezone.utc),
            actor=actor,
            detail=detail,
        )
        self._histories[execution_id].append(transition)
        return transition

    def validate_transition(
        self,
        from_status: TaskLifecycleStatus,
        to_status: TaskLifecycleStatus,
    ) -> bool:
        """Return True when *from_status → to_status* is legal, else raise."""
        allowed = VALID_TRANSITIONS.get(from_status)
        if allowed is None or to_status not in allowed:
            raise InvalidTransitionError(
                from_status=from_status.value,
                to_status=to_status.value,
                detail=f"Legal destinations from {from_status.value}: "
                f"{[s.value for s in (allowed or set())]}",
            )
        return True

    def get_timeline(self, execution_id: uuid.UUID) -> list[StatusTransition]:
        """Return every recorded transition for *execution_id*, in order."""
        self._ensure_tracked(execution_id)
        return list(self._histories[execution_id])

    def get_current_status(self, execution_id: uuid.UUID) -> TaskLifecycleStatus | None:
        """Return the current lifecycle status, or *None* if never recorded."""
        timeline = self.get_timeline(execution_id)
        if not timeline:
            return None
        return timeline[-1].status

    def compute_duration_ms(self, execution_id: uuid.UUID) -> float | None:
        """Millis between the first and last recorded transitions."""
        timeline = self.get_timeline(execution_id)
        if len(timeline) < 2:
            return None
        delta = timeline[-1].timestamp - timeline[0].timestamp
        return delta.total_seconds() * 1000

    def set_initial_status(
        self,
        execution_id: uuid.UUID,
        status: TaskLifecycleStatus = TaskLifecycleStatus.PENDING,
    ) -> StatusTransition:
        """Convenience: seed the timeline with an initial status (no *from* validation)."""
        self._ensure_tracked(execution_id)
        transition = StatusTransition(
            status=status,
            timestamp=datetime.now(timezone.utc),
            actor="system",
            detail="Initial status",
        )
        self._histories[execution_id].append(transition)
        return transition

    def entry_exists(self, execution_id: uuid.UUID) -> bool:
        """Check whether *execution_id* has been tracked."""
        return execution_id in self._histories

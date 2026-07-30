"""Agent lifecycle: archive, delete with cooldown, and audit trail."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NamedTuple


class AgentStatus(StrEnum):
    """Valid agent statuses."""

    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class ArchiveError(Exception):
    """Raised when an archive operation is attempted on an invalid status."""


class DeleteError(Exception):
    """Raised when a delete operation is attempted with invalid arguments or state."""


class CooldownError(Exception):
    """Raised when deletion is blocked by an active cooldown period."""

    code: str = "DELETION_COOLDOWN_ACTIVE"


class AuditRecord(NamedTuple):
    """Immutable audit trail entry."""

    agent_id: str
    action: str
    timestamp: float


# Module-level in-memory audit log — swap for a DB-backed store later.
audit_log: list[AuditRecord] = []


@dataclass
class Agent:
    """Agent with lifecycle state for archive and cooldown-gated deletion.

    Attributes:
        id: Unique identifier for this agent instance.
        status: Current lifecycle status — DEPRECATED or ARCHIVED.
        deprecated_at: Epoch seconds when the agent was marked deprecated.
        cooldown_seconds: Minimum seconds after ``deprecated_at`` before
            deletion is allowed.  ``0`` (default) permits immediate deletion.
        archive_id: Assigned by ``archive()``; ``None`` until archived.
        _deleted: Internal flag set by ``delete()`` — no ``DELETED`` status
            is introduced to keep the diff minimal per T-006 scope.
    """

    id: str
    status: AgentStatus = AgentStatus.DEPRECATED
    deprecated_at: float = field(default_factory=time.time)
    cooldown_seconds: float = 0
    archive_id: str | None = None
    _deleted: bool = field(default=False, repr=False)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def can_delete(self) -> bool:
        """Return ``True`` when the cooldown period has elapsed."""
        elapsed = time.time() - self.deprecated_at
        return elapsed >= self.cooldown_seconds

    # ------------------------------------------------------------------
    # Archive
    # ------------------------------------------------------------------

    def archive(self) -> str:
        """Transition from DEPRECATED → ARCHIVED and return the *archive_id*.

        Raises:
            ArchiveError: If ``status`` is not ``DEPRECATED``.
        """
        if self.status is not AgentStatus.DEPRECATED:
            raise ArchiveError(
                f"Cannot archive agent {self.id!r}: "
                f"current status is {self.status.value}, expected DEPRECATED."
            )
        self.status = AgentStatus.ARCHIVED
        self.archive_id = uuid.uuid4().hex
        return self.archive_id

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, confirm_text: str) -> None:
        """Delete this agent after passing guard checks.

        1. *confirm_text* must be exactly ``"DELETE"``.
        2. Status must be ``DEPRECATED`` or ``ARCHIVED``.
        3. The cooldown window must have elapsed.

        On success the operation is recorded in the module-level
        ``audit_log`` and the agent is flagged as deleted.

        Raises:
            DeleteError: Invalid confirm_text or disallowed status.
            CooldownError: Cooldown has not yet expired
                (``.code == "DELETION_COOLDOWN_ACTIVE"``).
        """
        # --- guard: confirmation text ----------------------------------
        if confirm_text != "DELETE":
            raise DeleteError(
                f"confirm_text must be 'DELETE', got {confirm_text!r}."
            )

        # --- guard: valid source status --------------------------------
        if self.status not in (AgentStatus.DEPRECATED, AgentStatus.ARCHIVED):
            raise DeleteError(
                f"Cannot delete agent {self.id!r}: "
                f"status {self.status.value} is not allowed for deletion."
            )

        # --- guard: cooldown -------------------------------------------
        if not self.can_delete():
            raise CooldownError(
                f"Deletion cooldown active for agent {self.id!r}. "
                f"Deprecated at {self.deprecated_at}, "
                f"cooldown is {self.cooldown_seconds}s."
            )

        # --- audit & flag ----------------------------------------------
        audit_log.append(
            AuditRecord(
                agent_id=self.id,
                action="delete",
                timestamp=time.time(),
            )
        )
        self._deleted = True

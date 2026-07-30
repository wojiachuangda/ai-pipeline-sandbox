"""In-memory stores with business rules for tools, bindings, and skills."""

from __future__ import annotations

from .tool_models import (
    BindingCreateRequest,
    BindingResponse,
    SkillCreateRequest,
    SkillResponse,
    SkillStatus,
    SkillStatusUpdateRequest,
    ToolCreateRequest,
    ToolResponse,
)


# ── Custom exceptions ────────────────────────────────────────────────────────


class BindingLimitError(Exception):
    """Raised when an agent exceeds the maximum number of tool bindings."""


class InvalidStatusTransitionError(Exception):
    """Raised when a skill status transition is not allowed."""


# ── ToolStore ────────────────────────────────────────────────────────────────


class ToolStore:
    """In-memory registry of tools."""

    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}

    def register(self, payload: ToolCreateRequest) -> dict:
        """Insert a tool and return its full record."""
        record = ToolResponse(
            **payload.model_dump(),
        ).model_dump()
        self._tools[record["tool_id"]] = record
        return record

    def get(self, tool_id: str) -> dict | None:
        """Look up a tool by id."""
        return self._tools.get(tool_id)

    def list(self) -> list[dict]:
        """Return all registered tools."""
        return list(self._tools.values())


# ── BindingStore ─────────────────────────────────────────────────────────────


class BindingStore:
    """In-memory registry of agent↔tool bindings."""

    MAX_BINDINGS: int = 50

    def __init__(self, max_bindings: int | None = None) -> None:
        if max_bindings is not None:
            self.MAX_BINDINGS = max_bindings
        self._bindings: dict[str, dict] = {}

    def _count_for_agent(self, agent_id: str) -> int:
        return sum(1 for b in self._bindings.values() if b["agent_id"] == agent_id)

    def bind(self, payload: BindingCreateRequest) -> dict:
        """Create a binding; raises BindingLimitError if agent is at capacity."""
        if self._count_for_agent(payload.agent_id) >= self.MAX_BINDINGS:
            raise BindingLimitError(
                f"Agent {payload.agent_id} already has {self.MAX_BINDINGS} bindings"
            )
        record = BindingResponse(
            **payload.model_dump(),
        ).model_dump()
        self._bindings[record["binding_id"]] = record
        return record

    def get(self, binding_id: str) -> dict | None:
        """Look up a binding by id."""
        return self._bindings.get(binding_id)

    def list_by_agent(self, agent_id: str) -> list[dict]:
        """Return all bindings for a given agent."""
        return [b for b in self._bindings.values() if b["agent_id"] == agent_id]

    def list_all(self) -> list[dict]:
        """Return every binding."""
        return list(self._bindings.values())

    def delete(self, binding_id: str) -> bool:
        """Remove a binding; returns True if it existed."""
        return self._bindings.pop(binding_id, None) is not None


# ── SkillStore ───────────────────────────────────────────────────────────────


class SkillStore:
    """In-memory registry of skills with status workflow."""

    def __init__(self) -> None:
        self._skills: dict[str, dict] = {}

    def create(self, payload: SkillCreateRequest) -> dict:
        """Create a skill with status = PENDING_REVIEW."""
        record = SkillResponse(
            **payload.model_dump(),
        ).model_dump()
        self._skills[record["skill_id"]] = record
        return record

    def get(self, skill_id: str) -> dict | None:
        """Look up a skill by id."""
        return self._skills.get(skill_id)

    def update_status(self, skill_id: str, payload: SkillStatusUpdateRequest) -> dict:
        """Transition status; only PENDING_REVIEW → APPROVED is valid."""
        skill = self._skills.get(skill_id)
        if skill is None:
            raise LookupError(f"Skill {skill_id} not found")
        current = SkillStatus(skill["status"])
        target = payload.status

        if current == SkillStatus.PENDING_REVIEW and target == SkillStatus.APPROVED:
            skill["status"] = target.value
            return skill

        raise InvalidStatusTransitionError(
            f"Cannot transition from {current.value} to {target.value}"
        )

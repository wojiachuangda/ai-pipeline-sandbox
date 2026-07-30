"""In-memory agent registry with uniqueness enforcement."""

from __future__ import annotations

from typing import Any

from .models import AgentCreateRequest, AgentUpdateRequest, _new_id, _now_iso


class DuplicateError(Exception):
    """Raised when a (tenant_id, name) pair already exists."""


class AgentStore:
    """Thread-unsafe in-memory store for agent records."""

    def __init__(self) -> None:
        self._agents: dict[str, dict[str, Any]] = {}
        # Secondary index: (tenant_id, name) → agent_id
        self._unique_index: dict[tuple[str, str], str] = {}

    # ── register ─────────────────────────────────────────────────

    def register(self, payload: AgentCreateRequest) -> dict[str, Any]:
        key = (payload.tenant_id, payload.name)
        if key in self._unique_index:
            raise DuplicateError(
                f"Agent named '{payload.name}' already exists in tenant '{payload.tenant_id}'"
            )

        record: dict[str, Any] = {
            "agent_id": _new_id(),
            "name": payload.name,
            "agent_type": payload.agent_type,
            "owner_id": payload.owner_id,
            "tenant_id": payload.tenant_id,
            "status": "INACTIVE",
            "created_at": _now_iso(),
            "description": None,
            "tags": [],
        }

        self._agents[record["agent_id"]] = record
        self._unique_index[key] = record["agent_id"]
        return record

    # ── get ──────────────────────────────────────────────────────

    def get(self, agent_id: str) -> dict[str, Any] | None:
        return self._agents.get(agent_id)

    # ── update ───────────────────────────────────────────────────

    def update(self, agent_id: str, patch: AgentUpdateRequest) -> dict[str, Any]:
        record = self._agents[agent_id]  # KeyError if missing → 404
        patch_data = patch.model_dump(exclude_unset=True)
        for field, value in patch_data.items():
            if value is not None:
                record[field] = value
        return record

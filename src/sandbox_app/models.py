"""Pydantic models for Agent Registry API."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid4())


# ── Request schemas ──────────────────────────────────────────────────


class AgentCreateRequest(BaseModel):
    """Payload for POST /agents."""

    name: str
    agent_type: str
    owner_id: str
    tenant_id: str


class AgentUpdateRequest(BaseModel):
    """Payload for PATCH /agents/{agent_id} — all fields optional."""

    description: str | None = None
    tags: list[str] | None = None
    owner_id: str | None = None


# ── Response schema ──────────────────────────────────────────────────


class AgentResponse(BaseModel):
    """Shape returned by all agent endpoints."""

    agent_id: str = Field(default_factory=_new_id)
    name: str
    agent_type: str
    owner_id: str
    tenant_id: str
    status: str = "INACTIVE"
    created_at: str = Field(default_factory=_now_iso)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)

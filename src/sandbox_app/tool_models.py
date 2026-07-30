"""Pydantic schemas for tools, bindings, and skills."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# ── Helpers ──────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Enums ────────────────────────────────────────────────────────────────────


class ToolType(str, Enum):
    API = "API"
    CLI = "CLI"
    FUNCTION = "FUNCTION"
    MCP = "MCP"


class BindingPermission(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ALLOW_WITH_APPROVAL = "ALLOW_WITH_APPROVAL"


class SkillStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"


# ── Tool schemas ─────────────────────────────────────────────────────────────


class ToolCreateRequest(BaseModel):
    name: str
    tool_type: ToolType
    input_schema: dict  # required — JSON Schema shape
    description: str | None = None
    endpoint: str | None = None  # MCP endpoint (stub, no dial)


class ToolResponse(BaseModel):
    tool_id: str = Field(default_factory=_new_id)
    name: str
    tool_type: ToolType
    input_schema: dict
    description: str | None = None
    endpoint: str | None = None
    created_at: str = Field(default_factory=_now_iso)


# ── Binding schemas ──────────────────────────────────────────────────────────


class RateLimit(BaseModel):
    max_requests: int
    window_seconds: int


class BindingCreateRequest(BaseModel):
    agent_id: str
    tool_id: str
    permission: BindingPermission
    rate_limit: RateLimit | None = None


class BindingResponse(BaseModel):
    binding_id: str = Field(default_factory=_new_id)
    agent_id: str
    tool_id: str
    permission: BindingPermission
    rate_limit: RateLimit | None = None
    created_at: str = Field(default_factory=_now_iso)


# ── Skill schemas ────────────────────────────────────────────────────────────


class SkillCreateRequest(BaseModel):
    name: str
    description: str | None = None
    file_path: str | None = None  # local path stub


class SkillResponse(BaseModel):
    skill_id: str = Field(default_factory=_new_id)
    name: str
    description: str | None = None
    status: SkillStatus = SkillStatus.PENDING_REVIEW
    file_path: str | None = None
    created_at: str = Field(default_factory=_now_iso)


class SkillStatusUpdateRequest(BaseModel):
    status: SkillStatus  # only APPROVED is valid from PENDING_REVIEW

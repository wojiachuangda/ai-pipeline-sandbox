"""FastAPI routes for tool registry, agent-tool bindings, and skill management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .tool_models import (
    BindingCreateRequest,
    SkillCreateRequest,
    SkillStatusUpdateRequest,
    ToolCreateRequest,
)
from .tool_store import (
    BindingLimitError,
    BindingStore,
    InvalidStatusTransitionError,
    SkillStore,
    ToolStore,
)

# ── Global stores (initialised once at app startup) ──────────────────────────

_tool_store: ToolStore
_binding_store: BindingStore
_skill_store: SkillStore


def init_stores(
    tool_store: ToolStore | None = None,
    binding_store: BindingStore | None = None,
    skill_store: SkillStore | None = None,
) -> None:
    """Seed the module-level stores (called from app factory)."""
    global _tool_store, _binding_store, _skill_store
    _tool_store = tool_store or ToolStore()
    _binding_store = binding_store or BindingStore()
    _skill_store = skill_store or SkillStore()


# ── Routers ──────────────────────────────────────────────────────────────────

tool_router = APIRouter(prefix="/tools", tags=["tools"])
binding_router = APIRouter(prefix="/bindings", tags=["bindings"])
skill_router = APIRouter(prefix="/skills", tags=["skills"])


# ── Tools endpoints ──────────────────────────────────────────────────────────


@tool_router.post("", status_code=201)
def register_tool(payload: ToolCreateRequest) -> dict:
    """Register a new tool.  Returns the created tool with a generated tool_id.

    ``input_schema`` is required (Pydantic enforces this — a 422 is returned
    when it is missing).
    """
    return _tool_store.register(payload)


@tool_router.get("/{tool_id}")
def get_tool(tool_id: str) -> dict:
    """Get a single tool by id."""
    record = _tool_store.get(tool_id)
    if record is None:
        raise HTTPException(status_code=404, detail="TOOL_NOT_FOUND")
    return record


@tool_router.get("")
def list_tools() -> list[dict]:
    """List all registered tools."""
    return _tool_store.list()


# ── Bindings endpoints ───────────────────────────────────────────────────────


@binding_router.post("", status_code=201)
def create_binding(payload: BindingCreateRequest) -> dict:
    """Bind an agent to a tool with a permission and optional rate-limit."""
    # Verify the tool exists
    if _tool_store.get(payload.tool_id) is None:
        raise HTTPException(status_code=404, detail="TOOL_NOT_FOUND")

    try:
        return _binding_store.bind(payload)
    except BindingLimitError:
        raise HTTPException(status_code=400, detail="BINDING_LIMIT_EXCEEDED")


@binding_router.get("")
def list_bindings(agent_id: str | None = None) -> list[dict]:
    """List bindings, optionally filtered by agent_id."""
    if agent_id is not None:
        return _binding_store.list_by_agent(agent_id)
    return _binding_store.list_all()


@binding_router.delete("/{binding_id}", status_code=204)
def delete_binding(binding_id: str) -> None:
    """Delete a binding by id."""
    if not _binding_store.delete(binding_id):
        raise HTTPException(status_code=404, detail="BINDING_NOT_FOUND")


# ── Skills endpoints ─────────────────────────────────────────────────────────


@skill_router.post("", status_code=201)
def create_skill(payload: SkillCreateRequest) -> dict:
    """Upload skill metadata.  Returns with status = PENDING_REVIEW."""
    return _skill_store.create(payload)


@skill_router.get("/{skill_id}")
def get_skill(skill_id: str) -> dict:
    """Get a skill by id."""
    record = _skill_store.get(skill_id)
    if record is None:
        raise HTTPException(status_code=404, detail="SKILL_NOT_FOUND")
    return record


@skill_router.patch("/{skill_id}/status")
def update_skill_status(skill_id: str, payload: SkillStatusUpdateRequest) -> dict:
    """Transition a skill's status (PENDING_REVIEW → APPROVED)."""
    try:
        return _skill_store.update_status(skill_id, payload)
    except LookupError:
        raise HTTPException(status_code=404, detail="SKILL_NOT_FOUND")
    except InvalidStatusTransitionError:
        raise HTTPException(status_code=400, detail="INVALID_STATUS_TRANSITION")

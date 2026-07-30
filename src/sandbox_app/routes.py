"""FastAPI routes for Agent Registry."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from .models import AgentCreateRequest, AgentResponse, AgentUpdateRequest
from .store import AgentStore, DuplicateError

router = APIRouter(prefix="/agents", tags=["agents"])

# Shared store instance — created once in app factory and injected via dependency
_store: AgentStore | None = None


def _get_store() -> AgentStore:
    assert _store is not None, "AgentStore not initialised — call init_store() first"
    return _store


def init_store() -> AgentStore:
    """Create and bind the singleton store. Called by the app factory."""
    global _store
    _store = AgentStore()
    return _store


# ── POST /agents ──────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AgentResponse)
def register_agent(body: AgentCreateRequest) -> AgentResponse:
    store = _get_store()
    try:
        record = store.register(body)
    except DuplicateError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AGENT_NAME_DUPLICATE",
        )
    return AgentResponse(**record)


# ── GET /agents/{agent_id} ─────────────────────────────────────────


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: str) -> AgentResponse:
    store = _get_store()
    record = store.get(agent_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentResponse(**record)


# ── PATCH /agents/{agent_id} ───────────────────────────────────────


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent(agent_id: str, body: AgentUpdateRequest) -> AgentResponse:
    store = _get_store()
    try:
        record = store.update(agent_id, body)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentResponse(**record)

"""Health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> dict[str, str]:
    # T-001: no external deps yet; ready == process up.
    return {"status": "ready", "module": "t-001-skeleton"}

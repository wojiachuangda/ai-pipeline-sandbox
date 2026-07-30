"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from .tool_routes import binding_router, init_stores, skill_router, tool_router


def create_app() -> FastAPI:
    """Build and return a FastAPI app with tool/binding/skill routers mounted."""
    app = FastAPI(title="Tool Registry & Skill API")
    init_stores()
    app.include_router(tool_router)
    app.include_router(binding_router)
    app.include_router(skill_router)
    return app

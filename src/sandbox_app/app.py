"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from .routes import init_store, router


def create_app() -> FastAPI:
    """Build and return a configured FastAPI app instance."""
    app = FastAPI(title="Agent Registry API")
    init_store()  # wire up the shared in-memory store
    app.include_router(router)
    return app

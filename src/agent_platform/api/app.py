"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from agent_platform import __version__
from agent_platform.api.health import router as health_router


def create_app() -> FastAPI:
    application = FastAPI(
        title="Multi-Agent Management Platform",
        version=__version__,
        description="Built module-by-module from goal.md (T-001 skeleton).",
    )
    application.include_router(health_router)
    return application


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("agent_platform.api.app:app", host="0.0.0.0", port=8090, reload=False)


if __name__ == "__main__":
    main()

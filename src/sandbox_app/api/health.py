"""Health-check HTTP application (Starlette).

Exposes:
- GET /live  — liveness probe (process is up)
- GET /ready — readiness probe (service can accept traffic)
"""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def live(request):  # noqa: ARG001
    """Liveness — returns 200 as long as the process is alive."""
    return JSONResponse({"status": "ok"})


async def ready(request):  # noqa: ARG001
    """Readiness — returns 200 when the service can receive requests."""
    return JSONResponse({"status": "ready"})


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = Starlette(
    routes=[
        Route("/live", live),
        Route("/ready", ready),
    ],
)

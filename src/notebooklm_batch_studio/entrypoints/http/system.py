"""System-level HTTP routes: root dashboard and health status endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from notebooklm_batch_studio.entrypoints.schemas import StatusResponse
from notebooklm_batch_studio.entrypoints.web_template import get_dashboard_html
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

system_router = APIRouter()


@system_router.get("/", response_class=HTMLResponse, tags=["Dashboard"], operation_id="get_dashboard")
def get_dashboard() -> str:
    """Serve the local web management dashboard.

    Returns:
        HTML page string.
    """
    return get_dashboard_html()


@system_router.get("/api/status", response_model=StatusResponse, tags=["System"], operation_id="get_status")
def get_status(request: Request) -> dict[str, Any]:
    """Retrieve overall system health, login credentials, and worker queue status.

    Args:
        request: Incoming HTTP request context.

    Returns:
        Status response dictionary.
    """
    service: BatchStudioService = request.app.state.service
    config = request.app.state.config
    auth_status = service.check_auth_status()
    courses = service.get_courses_summary()
    counts: dict[str, int] = {}
    for c in courses:
        for k, v in c["counts"].items():
            counts[k] = counts.get(k, 0) + v
    return {
        "app_env": config.app_env,
        "auth": auth_status,
        "queue_running": service.is_queue_running(),
        "total_courses": len(courses),
        "queue_counts": counts,
    }

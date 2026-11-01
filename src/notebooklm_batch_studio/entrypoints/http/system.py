"""System-level HTTP routes: root dashboard and health status endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from notebooklm_batch_studio.domain.exceptions import AuthExpiredError, StudioError
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


@system_router.get("/api/notebooklm/quota", tags=["System"], operation_id="get_notebooklm_quota")
async def get_notebooklm_quota(request: Request) -> dict[str, Any]:
    """Read the live NotebookLM usage meter (5-hour and weekly windows) and account limits.

    Args:
        request: Incoming HTTP request context.

    Returns:
        Quota summary: windows with remaining percent and reset time, per-action availability,
        notebook limit, and per-notebook source limit.

    Raises:
        HTTPException: 401 when NotebookLM login is missing or expired, 503 on other NotebookLM errors.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return await service.get_notebooklm_quota()
    except AuthExpiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except StudioError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

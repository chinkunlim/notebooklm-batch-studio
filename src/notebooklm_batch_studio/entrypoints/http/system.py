"""System-level HTTP routes: root dashboard and health status endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from notebooklm_batch_studio.domain.exceptions import AuthExpiredError, StudioError
from notebooklm_batch_studio.domain.models import JobStatus
from notebooklm_batch_studio.entrypoints.schemas import StatusResponse
from notebooklm_batch_studio.entrypoints.web_template import get_dashboard_html
from notebooklm_batch_studio.services.auth_status import sign_in_status
from notebooklm_batch_studio.services.backups import list_backups, prune_backups
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
        "quota_resume_at": _quota_resume_at(service),
    }


def _quota_resume_at(service: BatchStudioService) -> str | None:
    """Earliest time a job waiting for Gemini Notebook quota will be retried (Refs: SPEC-020).

    Args:
        service: Orchestrator owning the queue repository.

    Returns:
        ISO timestamp, or None when nothing waits for quota.
    """
    waits = [
        j.cooldown_until
        for j in service.queue_repo.list_jobs(status=JobStatus.QUOTA_WAIT)
        if j.cooldown_until
    ]
    return min(waits).isoformat() if waits else None


@system_router.get("/api/notebooklm/quota", tags=["System"], operation_id="get_notebooklm_quota")
async def get_notebooklm_quota(request: Request) -> dict[str, Any]:
    """Read the live Gemini Notebook usage meter (5-hour and weekly windows) and account limits.

    Args:
        request: Incoming HTTP request context.

    Returns:
        Quota summary: windows with remaining percent and reset time, per-action availability,
        notebook limit, and per-notebook source limit.

    Raises:
        HTTPException: 401 when Gemini Notebook login is missing or expired, 503 on other
            Gemini Notebook errors.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return await service.get_notebooklm_quota()
    except AuthExpiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except StudioError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@system_router.get("/api/system/sign-ins", tags=["System"], operation_id="get_sign_in_status")
def get_sign_in_status_route(request: Request) -> dict[str, Any]:
    """Return read-only authentication readiness across NotebookLM, Gemini Web, and library browser profiles.

    Args:
        request: Incoming HTTP request context.

    Returns:
        Dictionary containing `sign_ins` status entries.
    """
    rows = sign_in_status(request.app.state.config, request.app.state.gemini_auth)
    return {"sign_ins": rows}


class PruneBackupsRequest(BaseModel):
    """Body for pruning old database backups (Refs: SPEC-017)."""

    keep: int = Field(5, description="Number of newest backups to keep (at least 1)")
    dry_run: bool = Field(True, description="Only preview when True")


@system_router.get("/api/system/backups", tags=["System"], operation_id="list_backups")
def list_backups_route(request: Request) -> dict[str, Any]:
    """List database backups in `DATA_DIR/backups/`, newest first.

    Args:
        request: Incoming HTTP request context.

    Returns:
        Dictionary containing `backups`.
    """
    return {"backups": list_backups(request.app.state.config)}


@system_router.post("/api/system/backups/prune", tags=["System"], operation_id="prune_backups")
def prune_backups_route(body: PruneBackupsRequest, request: Request) -> dict[str, Any]:
    """Preview or move older backups into `DATA_DIR/deleted/backups/` (never deletes).

    Args:
        body: `keep` and `dry_run` options.
        request: Incoming HTTP request context.

    Returns:
        Prune summary with `kept`, `to_move`, `moved`.
    """
    try:
        return prune_backups(request.app.state.config, keep=body.keep, dry_run=body.dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

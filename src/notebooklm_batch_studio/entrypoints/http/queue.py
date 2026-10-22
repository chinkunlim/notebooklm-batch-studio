"""Task worker queue control HTTP routes: start, pause, resume, and retry."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from notebooklm_batch_studio.entrypoints.schemas import GenericActionResponse, QueueActionRequest
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

queue_router = APIRouter()


@queue_router.post(
    "/api/queue/start",
    response_model=GenericActionResponse,
    tags=["Queue"],
    operation_id="start_queue",
)
def start_queue(request: Request, req: QueueActionRequest | None = None) -> GenericActionResponse:
    """Start parallel task worker queue.

    Args:
        request: Incoming HTTP request context.
        req: Optional action confirmation payload.

    Returns:
        Generic action confirmation.
    """
    service: BatchStudioService = request.app.state.service
    service.start_queue()
    return GenericActionResponse(success=True, message="Worker queue started")


@queue_router.post(
    "/api/queue/pause",
    response_model=GenericActionResponse,
    tags=["Queue"],
    operation_id="pause_queue",
)
def pause_queue(request: Request, req: QueueActionRequest | None = None) -> GenericActionResponse:
    """Pause worker queue processing.

    Args:
        request: Incoming HTTP request context.
        req: Optional action confirmation payload.

    Returns:
        Generic action confirmation.
    """
    service: BatchStudioService = request.app.state.service
    service.pause_queue()
    return GenericActionResponse(success=True, message="Worker queue paused")


@queue_router.post(
    "/api/queue/resume",
    response_model=GenericActionResponse,
    tags=["Queue"],
    operation_id="resume_queue",
)
def resume_queue(request: Request) -> GenericActionResponse:
    """Wake up all quota-blocked tasks back to pending state.

    Args:
        request: Incoming HTTP request context.

    Returns:
        Generic action response detailing count of awakened jobs.
    """
    service: BatchStudioService = request.app.state.service
    count = service.resume_quota_wait()
    return GenericActionResponse(success=True, message=f"Awakened {count} jobs", data=count)


@queue_router.post(
    "/api/jobs/{job_id}/retry",
    response_model=GenericActionResponse,
    tags=["Queue"],
    operation_id="retry_job",
)
def retry_job(job_id: str, request: Request, req: QueueActionRequest | None = None) -> GenericActionResponse:
    """Reset a failed or cancelled task back to pending state.

    Args:
        job_id: Task UUID.
        request: Incoming HTTP request context.
        req: Optional action confirmation payload.

    Returns:
        Generic action confirmation.

    Raises:
        HTTPException: 404 if job ID does not exist.
    """
    service: BatchStudioService = request.app.state.service
    success = service.retry_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return GenericActionResponse(success=True, message=f"Job {job_id} reset to pending")

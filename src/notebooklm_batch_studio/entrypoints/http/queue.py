"""Task worker queue control HTTP routes: start, pause, resume, retry, and per-job prompt view/edit."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from notebooklm_batch_studio.entrypoints.schemas import GenericActionResponse, QueueActionRequest
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

logger = logging.getLogger(__name__)

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
    service.resume_queue()
    return GenericActionResponse(success=True, message=f"Resumed queue and awakened {count} jobs", data=count)


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


class JobPromptRequest(BaseModel):
    """New prompt text for one job."""

    prompt: str = Field(..., max_length=20000, description="Prompt sent to Gemini Notebook for this job")


@queue_router.get("/api/jobs/{job_id}/prompt", tags=["Queue"], operation_id="get_job_prompt")
def get_job_prompt(job_id: str, request: Request) -> dict[str, str | None]:
    """Show the prompt this job sends to Gemini Notebook.

    Args:
        job_id: Job id.
        request: Incoming HTTP request context.

    Returns:
        The job id and its custom prompt (None when it uses the built-in one).

    Raises:
        HTTPException: 404 when the job does not exist.
    """
    service: BatchStudioService = request.app.state.service
    job = service.queue_repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return {"job_id": job.id, "custom_prompt": job.custom_prompt}


@queue_router.post("/api/jobs/{job_id}/prompt", tags=["Queue"], operation_id="set_job_prompt")
def set_job_prompt(job_id: str, req: JobPromptRequest, request: Request) -> GenericActionResponse:
    """Replace the prompt a job sends to Gemini Notebook (used when it runs or is regenerated).

    Args:
        job_id: Job id.
        req: New prompt.
        request: Incoming HTTP request context.

    Returns:
        Action result.

    Raises:
        HTTPException: 404 when the job does not exist.
    """
    service: BatchStudioService = request.app.state.service
    if not service.update_job_prompt(job_id, req.prompt):
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    logger.info("Prompt updated for job %s (%d chars)", job_id, len(req.prompt))
    return GenericActionResponse(success=True, message="Prompt saved", data=job_id)

"""Course management HTTP routes: list, detail, preview, registration, and profile."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError, OllamaUnavailableError
from notebooklm_batch_studio.entrypoints.schemas import (
    AddCoursesRequest,
    CourseSummaryResponse,
    PreviewCoursesRequest,
    UpdateProfileRequest,
    UploadSourceRequest,
)
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

courses_router = APIRouter()


@courses_router.get(
    "/api/courses",
    response_model=list[CourseSummaryResponse],
    tags=["Courses"],
    operation_id="list_courses",
)
def list_courses(request: Request) -> list[dict[str, Any]]:
    """List all registered courses with their artifact generation progress.

    Args:
        request: Incoming HTTP request context.

    Returns:
        List of course summaries.
    """
    service: BatchStudioService = request.app.state.service
    return service.get_courses_summary()


@courses_router.get("/api/courses/{code}", tags=["Courses"], operation_id="get_course")
def get_course(code: str, request: Request) -> dict[str, Any]:
    """Retrieve detailed metadata, lecture breakdown, and job tasks for a course.

    Args:
        code: Course identifier.
        request: Incoming HTTP request context.

    Returns:
        Course detail dictionary.

    Raises:
        HTTPException: 404 if course not found.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.get_course_detail(code)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@courses_router.post("/api/courses/preview", tags=["Courses"], operation_id="preview_courses")
async def preview_courses(req: PreviewCoursesRequest, request: Request) -> list[dict[str, Any]]:
    """Inspect local directories and preview detected course lectures without saving.

    Args:
        req: Folder list payload.
        request: Incoming HTTP request context.

    Returns:
        List of preview results.
    """
    service: BatchStudioService = request.app.state.service
    return await service.preview_course_folders(
        req.folders,
        chapter_artifacts=req.chapter_artifacts,
        course_artifacts=req.course_artifacts,
    )


@courses_router.post("/api/courses", tags=["Courses"], operation_id="add_courses")
def add_courses(req: AddCoursesRequest, request: Request) -> list[dict[str, Any]]:
    """Register course directories, create records, and schedule artifact generation jobs.

    Args:
        req: Folder list and generation profile payload.
        request: Incoming HTTP request context.

    Returns:
        List of registered course summaries.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.add_course_folders(
            req.folders,
            profile=req.profile,
            chapter_artifacts=req.chapter_artifacts,
            course_artifacts=req.course_artifacts,
            language=req.language,
            paused=req.paused,
            reuse_notebook=req.reuse_notebook,
            options=req.options,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@courses_router.post("/api/courses/{code}/profile", tags=["Courses"], operation_id="update_course_profile")
def update_course_profile(code: str, req: UpdateProfileRequest, request: Request) -> dict[str, Any]:
    """Update active profile for a course and schedule newly required jobs.

    Args:
        code: Course identifier.
        req: Target profile payload.
        request: Incoming HTTP request context.

    Returns:
        Update result summary.

    Raises:
        HTTPException: 404 if course not found.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.set_course_profile(code, req.profile)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@courses_router.post("/api/courses/{code}/setup", tags=["Courses"], operation_id="setup_course_notebook")
async def setup_course_notebook(code: str, request: Request) -> dict[str, Any]:
    """Initialize Gemini Notebook notebook and upload all lecture PDF sources.

    Args:
        code: Course identifier.
        request: Incoming HTTP request context.

    Returns:
        Updated course summary with notebook ID.

    Raises:
        HTTPException: 404 if course not found.
    """
    service: BatchStudioService = request.app.state.service
    try:
        course = await service.setup_notebook_and_sources(code)
        return {"code": course.code, "name": course.name, "notebook_id": course.notebook_id}
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@courses_router.post(
    "/api/courses/{code}/refine_prompts", tags=["Courses"], operation_id="refine_course_prompts"
)
def refine_course_prompts(code: str, request: Request) -> dict[str, Any]:
    """Refine all task prompts for a course using Ollama gemma4 and master style blueprint.

    Args:
        code: Course identifier.
        request: Incoming HTTP request context.

    Returns:
        Summary detailing count of updated prompts.

    Raises:
        HTTPException: 404 if course not found, 503 if Ollama is unavailable.
    """
    service: BatchStudioService = request.app.state.service
    try:
        updated = service.refine_course_prompts_with_ollama(code)
        return {"code": code, "updated_prompts": updated}
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@courses_router.post(
    "/api/courses/{code}/lectures/{no}/retry_upload",
    tags=["Courses"],
    operation_id="retry_lecture_upload",
)
async def retry_lecture_upload(code: str, no: int, request: Request) -> dict[str, Any]:
    """Retry uploading a single lecture PDF to Gemini Notebook.

    Args:
        code: Course identifier.
        no: Sequence number of the lecture.
        request: Incoming HTTP request context.

    Returns:
        Upload status and source identifier payload.

    Raises:
        HTTPException: 404 if course not found, 422 if lecture or local file is missing.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return await service.upload_lecture_source(code, no, force=True)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@courses_router.get(
    "/api/courses/{code}/sources",
    tags=["Courses"],
    operation_id="list_course_sources",
)
async def list_course_sources(code: str, request: Request) -> dict[str, Any]:
    """List remote Gemini Notebook sources and local lecture sync states for a course.

    Args:
        code: Course identifier.
        request: Incoming HTTP request context.

    Returns:
        Dictionary containing notebook URL, remote sources, local lectures, and any remote error.

    Raises:
        HTTPException: 404 if course not found.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return await service.list_course_sources(code)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@courses_router.post(
    "/api/courses/{code}/sources",
    tags=["Courses"],
    operation_id="upload_course_source",
)
async def upload_course_source(code: str, req: UploadSourceRequest, request: Request) -> dict[str, Any]:
    """Upload a lecture PDF, local PDF file, or browser-uploaded PDF to the course notebook.

    Args:
        code: Course identifier.
        req: Source upload payload (`lecture_no`, `file_path`, or `filename` + `content_base64`).
        request: Incoming HTTP request context.

    Returns:
        Uploaded source metadata dictionary.

    Raises:
        HTTPException: 404 if course not found, 422 if upload payload or file is invalid.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return await service.upload_custom_source(code, **req.model_dump(exclude_none=True))
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@courses_router.delete(
    "/api/courses/{code}/sources/{source_id}",
    tags=["Courses"],
    operation_id="delete_course_source",
)
async def delete_course_source(code: str, source_id: str, request: Request) -> dict[str, Any]:
    """Delete a source from the course's Gemini Notebook and unlink matching local lectures.

    Args:
        code: Course identifier.
        source_id: Remote Gemini Notebook source identifier.
        request: Incoming HTTP request context.

    Returns:
        Deletion summary dictionary with unlinked lecture numbers.

    Raises:
        HTTPException: 404 if course not found, 422 if source_id or linked notebook is invalid.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return await service.delete_course_source(code, source_id)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@courses_router.post(
    "/api/courses/{code}/sync",
    tags=["Courses"],
    operation_id="sync_course_from_notebooklm",
)
async def sync_course_from_notebooklm(code: str, request: Request) -> dict[str, Any]:
    """Synchronize remote artifacts created manually in Gemini Notebook back to local files.

    Args:
        code: Course identifier.
        request: Incoming HTTP request context.

    Returns:
        Summary detailing count and list of synced items.

    Raises:
        HTTPException: 404 if course not found, 500 on sync failure.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return await service.sync_course_artifacts(code)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sync error: {exc}") from exc

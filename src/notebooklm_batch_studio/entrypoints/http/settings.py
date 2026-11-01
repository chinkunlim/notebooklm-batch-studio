"""HTTP routes for naming rules, per-course generation options, and versioned regeneration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.naming import naming_guide
from notebooklm_batch_studio.domain.usage_guide import usage_guide
from notebooklm_batch_studio.entrypoints.schemas import (
    ArtifactSelectionRequest,
    RegenerateRequest,
    UpdateOptionsRequest,
)
from notebooklm_batch_studio.services.course_settings import default_options, option_choices
from notebooklm_batch_studio.services.folder_browser import browse_folders
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

settings_router = APIRouter()


@settings_router.get("/api/naming-guide", tags=["Settings"], operation_id="get_naming_guide")
def get_naming_guide() -> dict[str, Any]:
    """Explain how artifacts are named on NotebookLM and locally (quiz levels, prefixes, versions).

    Returns:
        Naming rules and one row per artifact type.
    """
    return naming_guide()


@settings_router.get("/api/usage-guide", tags=["Settings"], operation_id="get_usage_guide")
def get_usage_guide() -> dict[str, Any]:
    """Explain how to use the studio and a study routine that makes the outputs effective.

    Returns:
        Title and sections of headings and steps.
    """
    return usage_guide()


@settings_router.get("/api/generation-options", tags=["Settings"], operation_id="get_default_options")
def get_default_options() -> dict[str, Any]:
    """Default generation options and allowed values, for setting up a course before adding it.

    Returns:
        `defaults` and `choices`.
    """
    choices = option_choices()
    choices.update(language=["zh-TW", "en", "bilingual"], mock_exam_questions={"min": 10, "max": 100})
    return {"defaults": default_options(), "choices": choices}


@settings_router.get("/api/courses/{code}/options", tags=["Settings"], operation_id="get_course_options")
def get_course_options(code: str, request: Request) -> dict[str, Any]:
    """Read a course's generation options and their allowed values.

    Args:
        code: Course code.
        request: Incoming HTTP request context.

    Returns:
        Current options and allowed choices.

    Raises:
        HTTPException: 404 when the course does not exist.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.course_settings.get_options(code)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@settings_router.put("/api/courses/{code}/options", tags=["Settings"], operation_id="set_course_options")
def set_course_options(code: str, req: UpdateOptionsRequest, request: Request) -> dict[str, Any]:
    """Change a course's generation options; they apply to generations started afterwards.

    Args:
        code: Course code.
        req: Options to change.
        request: Incoming HTTP request context.

    Returns:
        Updated options and allowed choices.

    Raises:
        HTTPException: 404 for an unknown course, 422 for an invalid option.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.course_settings.set_options(code, req.options)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@settings_router.post(
    "/api/courses/{code}/jobs/regenerate", tags=["Settings"], operation_id="regenerate_artifact"
)
def regenerate_artifact(code: str, req: RegenerateRequest, request: Request) -> dict[str, Any]:
    """Enqueue a new version (v2, v3, ...) of one artifact; older versions are kept.

    Args:
        code: Course code.
        req: Artifact type and lecture number.
        request: Incoming HTTP request context.

    Returns:
        The new job id, version and label.

    Raises:
        HTTPException: 404 for an unknown course, 422 for an invalid type or lecture.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.course_settings.regenerate(code, req.lecture_no, req.artifact_type)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@settings_router.get(
    "/api/courses/{code}/artifact-types", tags=["Settings"], operation_id="get_course_artifact_types"
)
def get_course_artifact_types(code: str, request: Request) -> dict[str, Any]:
    """Read which artifact types a course generates and every type that can be chosen.

    Args:
        code: Course code.
        request: Incoming HTTP request context.

    Returns:
        Selected chapter / course types and the labelled choices.

    Raises:
        HTTPException: 404 when the course does not exist.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.course_settings.get_artifact_selection(code)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@settings_router.put(
    "/api/courses/{code}/artifact-types", tags=["Settings"], operation_id="set_course_artifact_types"
)
def set_course_artifact_types(code: str, req: ArtifactSelectionRequest, request: Request) -> dict[str, Any]:
    """Change which artifact types a course generates: added types are queued, removed types skipped.

    Args:
        code: Course code.
        req: Chosen chapter and course-wide types.
        request: Incoming HTTP request context.

    Returns:
        Counts of queued / revived / skipped jobs and the new selection.

    Raises:
        HTTPException: 404 for an unknown course, 422 for an invalid type.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.course_settings.set_artifact_selection(code, req.chapter, req.course)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@settings_router.get("/api/folders", tags=["Settings"], operation_id="browse_folders")
def get_folders(
    request: Request,
    path: str | None = Query(default=None, description="Folder to open; empty for shortcuts"),
) -> dict[str, Any]:
    """List sub-folders (with PDF counts) so course folders can be picked by clicking.

    Args:
        request: Incoming HTTP request context.
        path: Absolute folder path inside the home directory, or empty for the shortcuts.

    Returns:
        Current folder, its parent, and its visible sub-folders.

    Raises:
        HTTPException: 400 when the folder is outside the home directory or unreadable.
    """
    try:
        return browse_folders(path, request.app.state.config.courses_input_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@settings_router.get("/api/jobs/{job_id}/options", tags=["Settings"], operation_id="get_job_options")
def get_job_options(job_id: str, request: Request) -> dict[str, Any]:
    """Read one output's own settings, the settings it will use, and the fields its type supports.

    Args:
        job_id: Job id.
        request: Incoming HTTP request context.

    Returns:
        Overrides, effective options, relevant fields and choices.

    Raises:
        HTTPException: 404 when the job does not exist.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.course_settings.get_job_options(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@settings_router.put("/api/jobs/{job_id}/options", tags=["Settings"], operation_id="set_job_options")
def set_job_options(job_id: str, req: UpdateOptionsRequest, request: Request) -> dict[str, Any]:
    """Set one output's own settings (empty values fall back to the course settings).

    Args:
        job_id: Job id.
        req: Option overrides.
        request: Incoming HTTP request context.

    Returns:
        Updated overrides and effective options.

    Raises:
        HTTPException: 404 for an unknown job, 422 for an invalid option.
    """
    service: BatchStudioService = request.app.state.service
    if service.queue_repo.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    try:
        return service.course_settings.set_job_options(job_id, req.options)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@settings_router.post("/api/courses/{code}/pause", tags=["Settings"], operation_id="pause_course")
def pause_course(code: str, request: Request) -> dict[str, Any]:
    """Hold one course: its jobs stay queued and do not start.

    Args:
        code: Course code.
        request: Incoming HTTP request context.

    Returns:
        Course code and paused state.

    Raises:
        HTTPException: 404 when the course does not exist.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.course_settings.set_paused(code, True)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@settings_router.post("/api/courses/{code}/start", tags=["Settings"], operation_id="start_course")
def start_course(code: str, request: Request) -> dict[str, Any]:
    """Let one course's jobs run (and make sure the queue itself is running).

    Args:
        code: Course code.
        request: Incoming HTTP request context.

    Returns:
        Course code and paused state.

    Raises:
        HTTPException: 404 when the course does not exist.
    """
    service: BatchStudioService = request.app.state.service
    try:
        result = service.course_settings.set_paused(code, False)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    service.start_queue()
    return result


@settings_router.delete("/api/courses/{code}", tags=["Settings"], operation_id="delete_course")
def delete_course(code: str, request: Request) -> dict[str, Any]:
    """Remove a course from this app (records deleted, outputs moved to DATA_DIR/deleted/).

    The source PDFs and everything on NotebookLM stay untouched.

    Args:
        code: Course code.
        request: Incoming HTTP request context.

    Returns:
        Removed job count and where the outputs were moved.

    Raises:
        HTTPException: 404 when the course does not exist.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.course_settings.delete_course(code)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

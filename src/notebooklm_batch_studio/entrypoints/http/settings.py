"""HTTP routes for naming rules, per-course generation options, and versioned regeneration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.naming import naming_guide
from notebooklm_batch_studio.entrypoints.schemas import RegenerateRequest, UpdateOptionsRequest
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

settings_router = APIRouter()


@settings_router.get("/api/naming-guide", tags=["Settings"], operation_id="get_naming_guide")
def get_naming_guide() -> dict[str, Any]:
    """Explain how artifacts are named on NotebookLM and locally (quiz levels, prefixes, versions).

    Returns:
        Naming rules and one row per artifact type.
    """
    return naming_guide()


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

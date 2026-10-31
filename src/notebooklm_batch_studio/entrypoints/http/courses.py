"""Course management HTTP routes: list, detail, preview, registration, and profile."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.entrypoints.schemas import (
    AddCoursesRequest,
    CourseSummaryResponse,
    PreviewCoursesRequest,
    UpdateProfileRequest,
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
def preview_courses(req: PreviewCoursesRequest, request: Request) -> list[dict[str, Any]]:
    """Inspect local directories and preview detected course lectures without saving.

    Args:
        req: Folder list payload.
        request: Incoming HTTP request context.

    Returns:
        List of preview results.
    """
    service: BatchStudioService = request.app.state.service
    return service.preview_course_folders(
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
    return service.add_course_folders(
        req.folders,
        profile=req.profile,
        chapter_artifacts=req.chapter_artifacts,
        course_artifacts=req.course_artifacts,
        language=req.language,
    )


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

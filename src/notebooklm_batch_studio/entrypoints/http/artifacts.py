"""Artifact management HTTP routes: quizzes, package file listings, and safe download."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

artifacts_router = APIRouter()


@artifacts_router.get(
    "/api/courses/{code}/lectures/{no}/quiz/{variant}",
    tags=["Quiz"],
    operation_id="get_quiz",
)
def get_quiz(
    code: str,
    no: int,
    variant: str,
    request: Request,
    with_answers: bool = Query(default=False, description="Whether to include answer rationales"),
) -> dict[str, Any]:
    """Retrieve generated quiz questions in markdown and JSON format.

    Args:
        code: Course identifier.
        no: Lecture number.
        variant: Quiz variant string.
        request: Incoming HTTP request context.
        with_answers: Whether to include answers and rationales.

    Returns:
        Quiz markdown and structure.

    Raises:
        HTTPException: 404 if course or quiz artifact is not found.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return service.get_quiz_content(code, no, variant, with_answers=with_answers)
    except (CourseNotFoundError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@artifacts_router.get("/api/courses/{code}/artifacts", tags=["Artifacts"], operation_id="list_artifacts")
def list_artifacts(
    code: str,
    request: Request,
    lecture_no: int | None = Query(default=None),
) -> list[dict[str, Any]]:
    """List generated deliverable files on disk for a specific course or lecture.

    Args:
        code: Course identifier.
        request: Incoming HTTP request context.
        lecture_no: Optional lecture number filter.

    Returns:
        List of file metadata records.
    """
    service: BatchStudioService = request.app.state.service
    return service.list_artifact_files(code, lecture_no=lecture_no)


@artifacts_router.get(
    "/api/artifacts/{code}/download/{file_path:path}",
    tags=["Artifacts"],
    operation_id="download_artifact",
)
def download_artifact(code: str, file_path: str, request: Request) -> FileResponse:
    """Download a generated artifact package file (PDF, CSV, OPML, MP3, etc.).

    Args:
        code: Course identifier.
        file_path: Relative path within the course's output directory.
        request: Incoming HTTP request context.

    Returns:
        FileResponse streaming the target file.

    Raises:
        HTTPException: 403 on traversal attempt, 404 if file missing.
    """
    config: AppConfig = request.app.state.config
    course_dir = (config.courses_output_dir / code).resolve()
    target_path = (course_dir / file_path).resolve()
    if not str(target_path).startswith(str(course_dir)):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected")
    if not target_path.exists() or not target_path.is_file():
        # Fallback: search recursively inside course_dir for file_path's filename
        candidates = list(course_dir.rglob(target_path.name))
        if candidates and candidates[0].is_file():
            target_path = candidates[0]
        else:
            raise HTTPException(status_code=404, detail="Requested file not found")
    return FileResponse(path=target_path, filename=target_path.name)

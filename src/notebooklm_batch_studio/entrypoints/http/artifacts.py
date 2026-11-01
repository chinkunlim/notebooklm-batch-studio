"""Artifact management HTTP routes: quizzes, package file listings, and safe download."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.services.converters.report_converter import report_to_html
from notebooklm_batch_studio.services.job_views import NEEDS_REVIEW_PREFIX
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


# Files a browser can show directly are sent inline (an <iframe> or new tab displays them);
# anything else is sent as an attachment.
INLINE_SUFFIXES = {".html", ".png", ".jpg", ".pdf", ".m4a", ".mp4", ".json", ".md", ".txt"}
MEDIA_TYPES = {".m4a": "audio/mp4", ".md": "text/markdown; charset=utf-8"}


def _resolve_artifact_path(config: AppConfig, code: str, file_path: str) -> Path:
    """Map a course-relative path (or `_needs_review/...`) to a real file, refusing traversal.

    Args:
        config: Application configuration.
        code: Course identifier.
        file_path: Path inside the course output folder, or `_needs_review/<code>_.../<file>`.

    Returns:
        The resolved file path.

    Raises:
        HTTPException: 403 on traversal attempt, 404 if the file is missing.
    """
    review_prefix = f"{NEEDS_REVIEW_PREFIX}/"
    if file_path.startswith(review_prefix):  # Refs: ISSUE-010
        review_root = config.needs_review_dir.resolve()
        target_path = (review_root / file_path.removeprefix(review_prefix)).resolve()
        if not target_path.is_relative_to(review_root):
            raise HTTPException(status_code=403, detail="Access denied: path traversal detected")
        top = target_path.relative_to(review_root).parts[0]
        if not top.startswith(f"{code}_") or not target_path.is_file():
            raise HTTPException(status_code=404, detail="Requested file not found")
        return target_path

    course_dir = (config.courses_output_dir / code).resolve()
    target_path = (course_dir / file_path).resolve()
    if not target_path.is_relative_to(course_dir):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected")
    if not target_path.is_file():
        # Fallback: search recursively inside course_dir for file_path's filename
        candidates = [c for c in course_dir.rglob(target_path.name) if c.is_file()]
        if not candidates:
            raise HTTPException(status_code=404, detail="Requested file not found")
        target_path = candidates[0]
    return target_path


@artifacts_router.get(
    "/api/artifacts/{code}/download/{file_path:path}",
    tags=["Artifacts"],
    operation_id="download_artifact",
)
def download_artifact(code: str, file_path: str, request: Request) -> FileResponse:
    """Download a generated artifact package file (PDF, CSV, OPML, M4A, etc.).

    Args:
        code: Course identifier.
        file_path: Relative path within the course's output directory, or
            `_needs_review/<code>_.../<file>` for a quarantined file of this course.
        request: Incoming HTTP request context.

    Returns:
        FileResponse streaming the target file (inline for browser-viewable types).

    Raises:
        HTTPException: 403 on traversal attempt, 404 if file missing.
    """
    target_path = _resolve_artifact_path(request.app.state.config, code, file_path)
    suffix = target_path.suffix.lower()
    # Python guesses audio/mp4a-latm for .m4a, which browsers' <audio> may refuse. Refs: ISSUE-007
    return FileResponse(
        path=target_path,
        filename=target_path.name,
        media_type=MEDIA_TYPES.get(suffix),
        content_disposition_type="inline" if suffix in INLINE_SUFFIXES else "attachment",
    )


@artifacts_router.get(
    "/api/artifacts/{code}/view/{file_path:path}",
    response_class=HTMLResponse,
    tags=["Artifacts"],
    operation_id="view_artifact",
)
def view_artifact(code: str, file_path: str, request: Request) -> str:
    """Show a Markdown report or a mind map as a formatted HTML page.

    For a mind map (`.opml` / `.json`) the Markdown outline saved next to it is shown.

    Args:
        code: Course identifier.
        file_path: Course-relative path of a `.md`, `.opml` or `.json` output.
        request: Incoming HTTP request context.

    Returns:
        Rendered HTML document.

    Raises:
        HTTPException: 403 on traversal, 404 if missing, 415 for a type that cannot be rendered.
    """
    target_path = _resolve_artifact_path(request.app.state.config, code, file_path)
    if target_path.suffix.lower() in {".opml", ".json"}:
        target_path = target_path.with_suffix(".md")
    if target_path.suffix.lower() != ".md" or not target_path.is_file():
        raise HTTPException(status_code=415, detail="Only Markdown reports and mind maps can be viewed")
    return report_to_html(target_path.stem, target_path.read_text(encoding="utf-8"))

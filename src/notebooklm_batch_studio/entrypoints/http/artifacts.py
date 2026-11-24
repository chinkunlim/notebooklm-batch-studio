"""Artifact management HTTP routes: quizzes, package file listings, and safe download."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.path_safety import PathSafetyError, validate_path_segment
from notebooklm_batch_studio.domain.study_hierarchy import resolve_course_output_root
from notebooklm_batch_studio.entrypoints.schemas import (
    CinematicVideoRequest,
    ExportArtifactRequest,
    GenerateScopedArtifactRequest,
    ReviseSlideRequest,
)
from notebooklm_batch_studio.services.converters.mindmap_converter import mindmap_to_html
from notebooklm_batch_studio.services.converters.report_converter import report_to_html
from notebooklm_batch_studio.services.job_views import NEEDS_REVIEW_PREFIX
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.remote_admin_service import RemoteAdminService

artifacts_router = APIRouter()


def _quiz_path_target(code: str, no: int, variant: str) -> tuple[str, int, str]:
    """Bundle lecture quiz path parameters for clean dependency injection.

    Args:
        code: Course identifier.
        no: Lecture number.
        variant: Quiz variant string.

    Returns:
        Tuple of `(code, no, variant)`.
    """
    return code, no, variant


@artifacts_router.get(
    "/api/courses/{code}/lectures/{no}/quiz/{variant}",
    tags=["Quiz"],
    operation_id="get_quiz",
)
def get_quiz(
    request: Request,
    target: tuple[str, int, str] = Depends(_quiz_path_target),
    with_answers: bool = Query(default=False, description="Whether to include answer rationales"),
) -> dict[str, Any]:
    """Retrieve generated quiz questions in markdown and JSON format.

    Args:
        request: Incoming HTTP request context.
        target: Resolved `(course_code, lecture_no, variant)` path tuple.
        with_answers: Whether to include answers and rationales.

    Returns:
        Quiz markdown and structure.

    Raises:
        HTTPException: 404 if course or quiz artifact is not found.
    """
    code, no, variant = target
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


def _course_output_root(request: Request, code: str) -> Path:
    """Return a course's output root: `<study_dir>/03 Notes/NotebookLM`, or `output/courses/<code>`.

    Args:
        request: Incoming HTTP request (provides config and the course repository).
        code: Validated course identifier.

    Returns:
        Resolved output root directory (Refs: ISSUE-050).
    """
    config: AppConfig = request.app.state.config
    service: BatchStudioService = request.app.state.service
    course = service.course_repo.get_course(code)
    study_dir = course.study_dir if course is not None else ""
    return resolve_course_output_root(config.courses_output_dir, code, study_dir).resolve()


def _resolve_review_path(config: AppConfig, code: str, rel_path: str) -> Path:
    """Map `_needs_review/<code>_.../<file>` to a quarantined file of this course, refusing traversal.

    Args:
        config: Application configuration.
        code: Validated course identifier.
        rel_path: Path below the needs-review folder.

    Returns:
        The resolved file path.

    Raises:
        HTTPException: 403 on traversal attempt, 404 if the file is missing or belongs to another course.
    """
    review_root = config.needs_review_dir.resolve()
    target_path = (review_root / rel_path).resolve()
    if not target_path.is_relative_to(review_root):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected")
    top = target_path.relative_to(review_root).parts[0]
    if not top.startswith(f"{code}_") or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Requested file not found")
    return target_path


def _resolve_artifact_path(request: Request, code: str, file_path: str) -> Path:
    """Map a course-relative path (or `_needs_review/...`) to a real file, refusing traversal.

    Args:
        request: Incoming HTTP request (provides config and the course repository).
        code: Course identifier.
        file_path: Path inside the course output folder, or `_needs_review/<code>_.../<file>`.

    Returns:
        The resolved file path.

    Raises:
        HTTPException: 403 on traversal attempt, 404 if the file is missing.
    """
    try:
        validate_path_segment(code, "code")
    except PathSafetyError as exc:
        raise HTTPException(status_code=404, detail="Requested file not found") from exc
    review_prefix = f"{NEEDS_REVIEW_PREFIX}/"
    if file_path.startswith(review_prefix):  # Refs: ISSUE-010
        return _resolve_review_path(request.app.state.config, code, file_path.removeprefix(review_prefix))
    course_dir = _course_output_root(request, code)
    target_path = (course_dir / file_path).resolve()
    if not target_path.is_relative_to(course_dir):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected")
    if target_path.is_file():
        return target_path
    # Fallback: search recursively inside course_dir for file_path's filename
    candidates = [c for c in course_dir.rglob(target_path.name) if c.is_file()]
    if not candidates:
        raise HTTPException(status_code=404, detail="Requested file not found")
    return candidates[0]


# HEAD lets the page check whether an optional file (e.g. the A4 infographic) exists.
@artifacts_router.api_route(
    "/api/artifacts/{code}/download/{file_path:path}",
    methods=["GET", "HEAD"],
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
    target_path = _resolve_artifact_path(request, code, file_path)
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
    target_path = _resolve_artifact_path(request, code, file_path)
    if target_path.suffix.lower() in {".opml", ".json"}:
        json_path = target_path.with_suffix(".json")
        if json_path.is_file():
            tree_data = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(tree_data, dict):
                return mindmap_to_html(json_path.stem, tree_data)
        target_path = target_path.with_suffix(".md")
    if target_path.suffix.lower() != ".md" or not target_path.is_file():
        raise HTTPException(status_code=415, detail="Only Markdown reports and mind maps can be viewed")
    return report_to_html(target_path.stem, target_path.read_text(encoding="utf-8"))


@artifacts_router.get(
    "/api/courses/{code}/remote-artifacts",
    tags=["Artifacts"],
    operation_id="list_remote_artifacts",
)
async def list_remote_artifacts_endpoint(code: str, request: Request) -> dict[str, Any]:
    """List remote Gemini Notebook artifacts annotated with active local version info.

    Args:
        code: Course identifier.
        request: Incoming HTTP request context.

    Returns:
        Dictionary with course code, notebook_id, and annotated remote artifacts.

    Raises:
        HTTPException: 404 if course not found, 502 if remote query fails.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return await service.list_remote_artifacts(code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Remote artifact listing failed: {exc}") from exc


@artifacts_router.delete(
    "/api/courses/{code}/remote-artifacts/{artifact_id}",
    tags=["Artifacts"],
    operation_id="delete_remote_artifact",
)
async def delete_remote_artifact_endpoint(
    code: str,
    artifact_id: str,
    request: Request,
    delete_local: bool = Query(default=False),
) -> dict[str, Any]:
    """Delete a remote Gemini Notebook artifact and optionally remove local output.

    Args:
        code: Course identifier.
        artifact_id: Remote Gemini Notebook artifact identifier.
        request: Incoming HTTP request context.
        delete_local: Whether to also delete downloaded local files and mark job skipped.

    Returns:
        Deletion summary dictionary.

    Raises:
        HTTPException: 404 if course not found, 502 on remote deletion failure.
    """
    service: BatchStudioService = request.app.state.service
    try:
        return await service.delete_remote_artifact(code, artifact_id, delete_local=delete_local)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Remote artifact deletion failed: {exc}") from exc


def _remote_admin(request: Request) -> RemoteAdminService:
    """Build a RemoteAdminService from app.state.service.

    Args:
        request: Incoming HTTP request context.

    Returns:
        Configured RemoteAdminService instance.
    """
    svc: BatchStudioService = request.app.state.service
    return RemoteAdminService(svc.course_repo, svc.notebooklm_client)


@artifacts_router.get(
    "/api/courses/{code}/remote-artifacts/suggest-reports",
    tags=["Artifacts"],
    operation_id="suggest_course_reports",
)
async def suggest_course_reports_endpoint(code: str, request: Request) -> dict[str, Any]:
    """Ask Gemini Notebook for AI-suggested report topics for a course.

    Args:
        code: Course identifier.
        request: Incoming HTTP request context.

    Returns:
        Dictionary with course_code and suggested reports.
    """
    try:
        return await _remote_admin(request).suggest_reports(code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@artifacts_router.post(
    "/api/courses/{code}/remote-artifacts/cinematic-video",
    tags=["Artifacts"],
    operation_id="generate_cinematic_video",
)
async def generate_cinematic_video_endpoint(
    code: str, payload: CinematicVideoRequest, request: Request
) -> dict[str, Any]:
    """Generate a cinematic video overview in Gemini Notebook.

    Args:
        code: Course identifier.
        payload: Video focus instructions and optional lecture scope.
        request: Incoming HTTP request context.

    Returns:
        Summary dictionary with generated artifact_id.
    """
    try:
        return await _remote_admin(request).generate_cinematic_video(
            code, instructions=payload.instructions, lecture_no=payload.lecture_no
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@artifacts_router.post(
    "/api/courses/{code}/remote-artifacts/{artifact_id}/revise-slide",
    tags=["Artifacts"],
    operation_id="revise_remote_slide",
)
async def revise_remote_slide_endpoint(
    code: str, artifact_id: str, payload: ReviseSlideRequest, request: Request
) -> dict[str, Any]:
    """Revise a single slide in an existing slide deck artifact.

    Args:
        code: Course identifier.
        artifact_id: Slide deck artifact identifier.
        payload: Zero-based slide index and revision prompt.
        request: Incoming HTTP request context.

    Returns:
        Summary dictionary with updated artifact_id.
    """
    try:
        return await _remote_admin(request).revise_slide(
            code, artifact_id, payload.slide_index, payload.prompt
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@artifacts_router.post(
    "/api/courses/{code}/remote-artifacts/{artifact_id}/export",
    tags=["Artifacts"],
    operation_id="export_remote_artifact",
)
async def export_remote_artifact_endpoint(
    code: str, artifact_id: str, payload: ExportArtifactRequest, request: Request
) -> dict[str, Any]:
    """Export a remote report or data table to Google Docs or Sheets.

    Args:
        code: Course identifier.
        artifact_id: Remote artifact identifier.
        payload: Export title and artifact kind.
        request: Incoming HTTP request context.

    Returns:
        Export result dictionary.
    """
    try:
        return await _remote_admin(request).export_artifact(
            code, artifact_id, title=payload.title, kind=payload.kind
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@artifacts_router.post(
    "/api/courses/{code}/remote-artifacts/{artifact_id}/retry",
    tags=["Artifacts"],
    operation_id="retry_remote_artifact",
)
async def retry_remote_artifact_endpoint(code: str, artifact_id: str, request: Request) -> dict[str, Any]:
    """Retry a failed remote artifact directly on Gemini Notebook.

    Args:
        code: Course identifier.
        artifact_id: Failed artifact identifier.
        request: Incoming HTTP request context.

    Returns:
        Retry status dictionary.
    """
    try:
        return await _remote_admin(request).retry_remote_artifact(code, artifact_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@artifacts_router.post(
    "/api/courses/{code}/remote-artifacts/generate",
    tags=["Artifacts"],
    operation_id="generate_scoped_remote_artifact",
)
async def generate_scoped_remote_artifact_endpoint(
    code: str, payload: GenerateScopedArtifactRequest, request: Request
) -> dict[str, Any]:
    """Generate a Studio artifact or custom report scoped to selected sources.

    Args:
        code: Course identifier.
        payload: Artifact kind, optional source_ids, and instructions.
        request: Incoming HTTP request context.

    Returns:
        Dictionary with created `artifact_id` and `source_count`.
    """
    try:
        return await _remote_admin(request).generate_from_sources(
            code, payload.kind, {"source_ids": payload.source_ids, "instructions": payload.instructions}
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

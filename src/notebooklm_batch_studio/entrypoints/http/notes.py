"""FastAPI routes for Phase 1 modular Markdown note generation (Refs: ADR-012)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.note_driver_factory import (
    build_note_driver_factory,
    build_note_upload_fn,
)
from notebooklm_batch_studio.domain.note_pipeline import NoteBackend
from notebooklm_batch_studio.domain.path_safety import PathSafetyError
from notebooklm_batch_studio.services.notes.module_prompts import (
    ModulePromptError,
    StepPromptContext,
)
from notebooklm_batch_studio.services.notes.note_files import list_note_files, read_note_file
from notebooklm_batch_studio.services.notes.note_pipeline_service import (
    ChapterNoteRequest,
    NotePipelineService,
)

logger = logging.getLogger(__name__)
notes_router = APIRouter(prefix="/api/notes", tags=["notes"])


class PromptPreviewRequest(BaseModel):
    """Request body for rendering a standalone modular prompt `.md` template.

    Attributes:
        step_id: Step code such as `01_mindmap`.
        course_name: Course name replacing `{{COURSE_NAME}}`.
        chapter_id: Chapter identifier replacing `{{CHAPTER_ID}}`.
        chapter_title: Chapter title replacing `{{CHAPTER_TITLE}}`.
    """

    step_id: str = Field(..., min_length=1)
    course_name: str = Field(..., min_length=1)
    chapter_id: str = Field(..., min_length=1)
    chapter_title: str = ""


class ChapterGenerateRequest(BaseModel):
    """Request body for generating or rerunning modular Markdown notes.

    Attributes:
        course_key: Course identifier or folder code.
        course_name: Human-readable course name.
        chapter_id: Chapter identifier (e.g. `ch01`).
        chapter_title: Human-readable chapter title.
        pdf_path: Optional chapter PDF path for `gemini_web`.
        backend: Generation backend (`gemini_web` default, `notebooklm` fallback).
        model: Gemini model name (e.g. `4 Argon`).
        notebook_id: Target NotebookLM ID when `backend == notebooklm`.
        source_ids: Single-chapter NotebookLM source IDs when `backend == notebooklm`.
        steps_override: Optional subset of step IDs for single-module rerun.
    """

    course_key: str = Field(..., min_length=1)
    course_name: str = Field(..., min_length=1)
    chapter_id: str = Field(..., min_length=1)
    chapter_title: str = ""
    pdf_path: str = ""
    backend: NoteBackend = NoteBackend.GEMINI_WEB
    model: str = "4 Argon"
    notebook_id: str = ""
    source_ids: list[str] = Field(default_factory=list)
    steps_override: list[str] | None = None
    study_dir: str = ""


def _resolve_course_dir(request: Request, course_key: str, attr: str) -> Path | None:
    """Look up a registered course folder (`study_dir` or `source_dir`) from `CourseRepository`.

    Args:
        request: Incoming HTTP request carrying `session_factory`.
        course_key: Course code / identifier.
        attr: Course record attribute name, `study_dir` or `source_dir`.

    Returns:
        Path to the folder, or None if the course or folder is not registered.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return None
    with factory() as session:
        course = CourseRepository(session).get_course(course_key)
        value = getattr(course, attr, None) if course else None
    return Path(value) if value else None


def _service(request: Request) -> NotePipelineService:
    """Return or lazily construct `NotePipelineService` on app state.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Configured `NotePipelineService` instance.
    """
    existing = getattr(request.app.state, "note_pipeline_service", None)
    if existing is not None:
        return cast(NotePipelineService, existing)
    cfg = request.app.state.config
    return NotePipelineService(
        cfg,
        driver_factory=build_note_driver_factory(cfg),
        study_dir_resolver=lambda code: _resolve_course_dir(request, code, "study_dir"),
        source_dir_resolver=lambda code: _resolve_course_dir(request, code, "source_dir"),
    )


@notes_router.get("/prompts")
def list_note_prompts(request: Request) -> dict[str, Any]:
    """List standalone modular prompt `.md` templates.

    Args:
        request: Incoming HTTP request.

    Returns:
        Dictionary containing `prompts` metadata list.
    """
    return {"prompts": _service(request).list_prompts()}


@notes_router.post("/prompts/preview")
def preview_note_prompt(body: PromptPreviewRequest, request: Request) -> dict[str, str]:
    """Render one modular prompt `.md` file with chapter metadata filled in.

    Args:
        body: Prompt preview parameters.
        request: Incoming HTTP request.

    Returns:
        Rendered prompt dictionary.
    """
    ctx = StepPromptContext(body.course_name, body.chapter_id, body.chapter_title)
    try:
        return _service(request).preview_prompt(body.step_id, ctx)
    except ModulePromptError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _run_notes_call(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Execute a note service call and translate path-safety or missing-file errors to HTTP status.

    Args:
        fn: Zero-argument service call returning a dictionary.

    Returns:
        Dictionary returned by `fn`.

    Raises:
        HTTPException: 400 on `PathSafetyError` or `ValueError`, 404 on `FileNotFoundError`.
    """
    try:
        return fn()
    except (PathSafetyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@notes_router.get("/status/{course_key}")
def get_note_status(course_key: str, request: Request) -> dict[str, Any]:
    """Get generation status and pause flag for a course.

    Args:
        course_key: Course identifier.
        request: Incoming HTTP request.

    Returns:
        Course state dictionary.
    """
    return _run_notes_call(lambda: _service(request).get_status(course_key))


@notes_router.post("/generate")
def generate_chapter_notes(body: ChapterGenerateRequest, request: Request) -> dict[str, Any]:
    """Run Phase 1 modular Markdown note generation and stitching for one chapter.

    Args:
        body: Chapter generation parameters.
        request: Incoming HTTP request.

    Returns:
        Generation outcome dictionary.
    """
    req = ChapterNoteRequest(
        course_key=body.course_key,
        course_name=body.course_name,
        chapter_id=body.chapter_id,
        chapter_title=body.chapter_title,
        pdf_path=Path(body.pdf_path) if body.pdf_path else None,
        backend=body.backend,
        model=body.model,
        notebook_id=body.notebook_id,
        source_ids=list(body.source_ids),
        steps_override=body.steps_override,
        study_dir=Path(body.study_dir) if body.study_dir else None,
    )
    try:
        return _service(request).run_chapter(req)
    except Exception as exc:
        logger.error("Note generation failed for %s/%s: %s", body.course_key, body.chapter_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@notes_router.post("/pause/{course_key}")
def pause_note_generation(course_key: str, request: Request) -> dict[str, Any]:
    """Request a clean pause for a course's note generation.

    Args:
        course_key: Course identifier.
        request: Incoming HTTP request.

    Returns:
        Updated pause status.
    """
    return _run_notes_call(lambda: _service(request).request_pause(course_key))


@notes_router.post("/resume/{course_key}")
def resume_note_generation(course_key: str, request: Request) -> dict[str, Any]:
    """Clear an active pause request for a course.

    Args:
        course_key: Course identifier.
        request: Incoming HTTP request.

    Returns:
        Updated pause status.
    """
    return _run_notes_call(lambda: _service(request).clear_pause(course_key))


@notes_router.get("/content/{course_key}/{chapter_id}")
def read_stitched_note_content(
    course_key: str,
    chapter_id: str,
    request: Request,
) -> dict[str, Any]:
    """Read the stitched chapter Markdown note if it exists.

    Args:
        course_key: Course identifier.
        chapter_id: Chapter identifier.
        request: Incoming HTTP request.

    Returns:
        Dictionary with `exists`, `path`, and `content`.
    """
    return _run_notes_call(lambda: _service(request).read_stitched_note(course_key, chapter_id))


class PushNoteSourceRequest(BaseModel):
    """Request body for pushing a stitched chapter `.md` note to Gemini Notebook.

    Attributes:
        course_key: Course identifier.
        chapter_id: Chapter identifier (e.g. `ch01`).
        notebook_id: Optional explicit Gemini Notebook ID (defaults to course's notebook).
    """

    course_key: str = Field(..., min_length=1)
    chapter_id: str = Field(..., min_length=1)
    notebook_id: str = ""


class ImportLegacyNotesRequest(BaseModel):
    """Request body for importing standalone `note-studio` `.md` files.

    Attributes:
        source_dir: Local folder containing `.md` notes.
        course_key: Target course identifier.
        overwrite: Whether to overwrite existing files.
    """

    source_dir: str = Field(..., min_length=1)
    course_key: str = Field(..., min_length=1)
    overwrite: bool = False


def _resolve_course_notebook_id(request: Request, course_key: str) -> str:
    """Look up `notebook_id` from `CourseRepository` for `course_key`.

    Args:
        request: Incoming HTTP request.
        course_key: Course identifier.

    Returns:
        Notebook ID string or empty string.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return ""
    with factory() as session:
        course = CourseRepository(session).get_course(course_key)
        return (course.notebook_id or "") if course else ""


@notes_router.get("/files/{course_key}")
def list_course_note_files(course_key: str, request: Request) -> dict[str, Any]:
    """List every `.md` / `.pdf` note file in the course NoteStudio folder (Refs: SPEC-017).

    Args:
        course_key: Course identifier.
        request: Incoming HTTP request.

    Returns:
        Dictionary containing `files` list.
    """
    return _run_notes_call(
        lambda: {"files": list_note_files(_service(request).paths.notes_course_dir(course_key))}
    )


@notes_router.get("/file/{course_key}", response_model=None)
def get_course_note_file(course_key: str, path: str, request: Request) -> dict[str, Any] | FileResponse:
    """Return a Markdown note as JSON, or stream a PDF note file (Refs: SPEC-017).

    Args:
        course_key: Course identifier.
        path: File path relative to the NoteStudio folder.
        request: Incoming HTTP request.

    Returns:
        `{relative_path, kind, path, content}` for Markdown, or the PDF file itself.
    """
    data = _run_notes_call(lambda: read_note_file(_service(request).paths.notes_course_dir(course_key), path))
    if data["kind"] == "pdf":
        return FileResponse(data["path"], media_type="application/pdf")
    return data


@notes_router.get("/chapters/{course_key}")
def list_note_chapters(course_key: str, request: Request) -> dict[str, Any]:
    """List stitched chapter `.md` notes for a course.

    Args:
        course_key: Course identifier.
        request: Incoming HTTP request.

    Returns:
        Dictionary containing `chapters` list.
    """
    return _run_notes_call(lambda: {"chapters": _service(request).list_chapters(course_key)})


@notes_router.post("/push_to_source")
def push_note_to_source_endpoint(body: PushNoteSourceRequest, request: Request) -> dict[str, Any]:
    """Render a chapter `.md` note to PDF and upload it to Gemini Notebook.

    Args:
        body: Push request parameters.
        request: Incoming HTTP request.

    Returns:
        Upload result dictionary with `source_id`.
    """
    notebook_id = body.notebook_id.strip() or _resolve_course_notebook_id(request, body.course_key)
    upload_fn = getattr(request.app.state, "note_upload_fn", None) or build_note_upload_fn(
        request.app.state.config
    )
    try:
        return _service(request).push_to_source(body.course_key, body.chapter_id, notebook_id, upload_fn)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@notes_router.post("/import_legacy")
def import_legacy_notes_endpoint(body: ImportLegacyNotesRequest, request: Request) -> dict[str, Any]:
    """Import `.md` notes from a standalone `note-studio` folder into `03 Notes/NoteStudio`.

    Args:
        body: Import request parameters.
        request: Incoming HTTP request.

    Returns:
        Import summary dictionary.
    """
    return _run_notes_call(
        lambda: _service(request).import_legacy(
            Path(body.source_dir), body.course_key, overwrite=body.overwrite
        )
    )

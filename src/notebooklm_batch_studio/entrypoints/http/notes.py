"""FastAPI routes for Phase 1 modular Markdown note generation (Refs: ADR-012)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.note_driver_factory import build_note_driver_factory
from notebooklm_batch_studio.domain.note_pipeline import NoteBackend
from notebooklm_batch_studio.services.notes.module_prompts import (
    ModulePromptError,
    StepPromptContext,
)
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


def _resolve_course_study_dir(request: Request, course_key: str) -> Path | None:
    """Look up `study_dir` from `CourseRepository` for `course_key`, if registered.

    Args:
        request: Incoming HTTP request carrying `session_factory`.
        course_key: Course code / identifier.

    Returns:
        Path to course study directory, or None if not registered.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return None
    with factory() as session:
        course = CourseRepository(session).get_course(course_key)
        if course and course.study_dir:
            return Path(course.study_dir)
    return None


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
        study_dir_resolver=lambda code: _resolve_course_study_dir(request, code),
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


@notes_router.get("/status/{course_key}")
def get_note_status(course_key: str, request: Request) -> dict[str, Any]:
    """Get generation status and pause flag for a course.

    Args:
        course_key: Course identifier.
        request: Incoming HTTP request.

    Returns:
        Course state dictionary.
    """
    return _service(request).get_status(course_key)


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
    return _service(request).request_pause(course_key)


@notes_router.post("/resume/{course_key}")
def resume_note_generation(course_key: str, request: Request) -> dict[str, Any]:
    """Clear an active pause request for a course.

    Args:
        course_key: Course identifier.
        request: Incoming HTTP request.

    Returns:
        Updated pause status.
    """
    return _service(request).clear_pause(course_key)


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
    return _service(request).read_stitched_note(course_key, chapter_id)

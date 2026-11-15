"""FastAPI routes for exploratory Q&A chat, Markdown notes, tags, and source pushing (SPEC-011)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError, SourceLimitExceededError
from notebooklm_batch_studio.entrypoints.schemas import (
    AskQARequest,
    BundleNotesRequest,
    MasteryUpdateRequest,
    MemoUpdateRequest,
    SaveQANoteRequest,
    SummarizeQARequest,
)
from notebooklm_batch_studio.services.qa_notes_service import AskOptions, QANotesService

logger = logging.getLogger(__name__)
qa_notes_router = APIRouter()


def _qa_service(request: Request) -> QANotesService:
    """Retrieve QANotesService from FastAPI app state.

    Args:
        request: Incoming HTTP request.

    Returns:
        Configured QANotesService instance.
    """
    return request.app.state.qa_notes  # type: ignore[no-any-return]


@qa_notes_router.post("/api/courses/{code}/qa/ask", tags=["Q&A Notes"], operation_id="ask_qa")
async def ask_qa_endpoint(code: str, req: AskQARequest, request: Request) -> dict[str, Any]:
    """Ask a scoped exploratory question to Gemini Notebook.

    Args:
        code: Course code.
        req: Question payload.
        request: HTTP request context.

    Returns:
        Dictionary with `answer`, `conversation_id`, and `references`.
    """
    try:
        opts = AskOptions(
            lecture_no=req.lecture_no,
            conversation_id=req.conversation_id,
            use_web_search=req.use_web_search,
        )
        return await _qa_service(request).ask(code, req.question, opts)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@qa_notes_router.post("/api/courses/{code}/qa/summarize", tags=["Q&A Notes"], operation_id="summarize_qa")
async def summarize_qa_endpoint(code: str, req: SummarizeQARequest, request: Request) -> dict[str, Any]:
    """Ask NotebookLM to format an active conversation into Markdown notes.

    Args:
        code: Course code.
        req: Summarize payload with conversation_id.
        request: HTTP request context.

    Returns:
        Formatted Markdown, title, and extracted tags.
    """
    try:
        return await _qa_service(request).summarize_and_format(
            code, req.conversation_id, req.lecture_no, req.scene
        )
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@qa_notes_router.get("/api/courses/{code}/notes", tags=["Q&A Notes"], operation_id="list_qa_notes")
def list_notes_endpoint(
    code: str,
    request: Request,
    tag: str | None = None,
    lecture_no: int | None = None,
) -> dict[str, Any]:
    """List saved Markdown notes for a course (pass `code='*'` for cross-course search).

    Args:
        code: Course code or `*`.
        request: HTTP request context (reads optional `mastery` query param).
        tag: Optional tag filter.
        lecture_no: Optional lecture filter.

    Returns:
        Dictionary with `notes` list.
    """
    mastery = request.query_params.get("mastery")
    notes = _qa_service(request).list_notes(code, tag=tag, lecture_no=lecture_no, mastery=mastery)
    return {"notes": notes}


@qa_notes_router.post("/api/courses/{code}/notes", tags=["Q&A Notes"], operation_id="save_qa_note")
def save_note_endpoint(code: str, req: SaveQANoteRequest, request: Request) -> dict[str, Any]:
    """Save or update a Q&A Markdown note on disk and in the database.

    Args:
        code: Course code.
        req: Note content and metadata.
        request: HTTP request context.

    Returns:
        Saved note dictionary.
    """
    try:
        return _qa_service(request).save_note(
            code,
            req.title,
            req.content_markdown,
            lecture_no=req.lecture_no,
            tags=req.tags,
            source_scene=req.source_scene,
            personal_memo=req.personal_memo,
            note_id=req.note_id,
        )
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@qa_notes_router.patch(
    "/api/courses/{code}/notes/{note_id}/mastery", tags=["Q&A Notes"], operation_id="update_note_mastery"
)
def update_mastery_endpoint(
    code: str, note_id: str, req: MasteryUpdateRequest, request: Request
) -> dict[str, Any]:
    """Toggle note mastery status between `needs_review` and `mastered`.

    Args:
        code: Course code.
        note_id: Note ID.
        req: Mastery update payload.
        request: HTTP request context.

    Returns:
        Updated note dictionary.
    """
    try:
        return _qa_service(request).toggle_mastery(note_id, req.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@qa_notes_router.patch(
    "/api/courses/{code}/notes/{note_id}/memo", tags=["Q&A Notes"], operation_id="update_note_memo"
)
def update_memo_endpoint(code: str, note_id: str, req: MemoUpdateRequest, request: Request) -> dict[str, Any]:
    """Update personal memo text on a Q&A note.

    Args:
        code: Course code.
        note_id: Note ID.
        req: Memo payload.
        request: HTTP request context.

    Returns:
        Updated note dictionary.
    """
    try:
        return _qa_service(request).update_memo(note_id, req.personal_memo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@qa_notes_router.post(
    "/api/courses/{code}/notes/{note_id}/push_to_source",
    tags=["Q&A Notes"],
    operation_id="push_qa_note_to_source",
)
async def push_note_endpoint(code: str, note_id: str, request: Request) -> dict[str, Any]:
    """Upload a single saved note to the course's Gemini Notebook sources.

    Args:
        code: Course code.
        note_id: Note ID.
        request: HTTP request context.

    Returns:
        Updated note dictionary with `uploaded_source_id`.
    """
    try:
        return await _qa_service(request).push_note_to_source(code, note_id)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, SourceLimitExceededError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@qa_notes_router.post(
    "/api/courses/{code}/notes/bundle_to_source",
    tags=["Q&A Notes"],
    operation_id="bundle_qa_notes_to_source",
)
async def bundle_notes_endpoint(code: str, req: BundleNotesRequest, request: Request) -> dict[str, Any]:
    """Combine multiple notes into one PDF and upload as a single source.

    Args:
        code: Course code.
        req: Bundle request with note_ids and title.
        request: HTTP request context.

    Returns:
        Upload result summary.
    """
    try:
        return await _qa_service(request).bundle_notes_to_source(code, req.note_ids, req.title)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, SourceLimitExceededError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@qa_notes_router.delete(
    "/api/courses/{code}/notes/{note_id}", tags=["Q&A Notes"], operation_id="delete_qa_note"
)
def delete_note_endpoint(code: str, note_id: str, request: Request) -> dict[str, Any]:
    """Delete a saved Q&A note and its Markdown file.

    Args:
        code: Course code.
        note_id: Note ID.
        request: HTTP request context.

    Returns:
        Deletion confirmation dictionary.
    """
    deleted = _qa_service(request).delete_note(note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")
    return {"deleted": True, "note_id": note_id}

"""HTTP routes for the background Gemini note schedule (SPEC-020)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.entrypoints.note_runtime import build_note_pipeline, build_note_scheduler
from notebooklm_batch_studio.services.notes.note_scheduler import NoteScheduler, ScheduleBusyError

logger = logging.getLogger(__name__)

note_schedule_router = APIRouter(prefix="/api/notes/schedule", tags=["notes"])


class ScheduleRequest(BaseModel):
    """Body for approving chapters for background note generation."""

    course_key: str = Field(..., min_length=1, description="Course code")
    lecture_nos: list[int] = Field(..., min_length=1, description="Lecture numbers to generate")


def register_note_schedule_errors(app: FastAPI) -> None:
    """Answer 503 when the schedule file stays locked by another process (SPEC-025 R1).

    Args:
        app: FastAPI application.
    """

    async def busy(_request: Request, exc: Exception) -> JSONResponse:
        """Turn ScheduleBusyError into 503.

        Args:
            _request: Incoming HTTP request.
            exc: The ScheduleBusyError.

        Returns:
            503 response with a readable message.
        """
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    app.add_exception_handler(ScheduleBusyError, busy)


def _scheduler(request: Request) -> NoteScheduler:
    """Return the app's scheduler, creating one when the app did not.

    Args:
        request: Incoming HTTP request.

    Returns:
        NoteScheduler.
    """
    existing = getattr(request.app.state, "note_scheduler", None)
    if existing is None:
        existing = build_note_scheduler(request.app.state.config, request.app.state.session_factory)
        request.app.state.note_scheduler = existing
    return existing


def _course(request: Request, code: str) -> Course:
    """Load a course or raise 404.

    Args:
        request: Incoming HTTP request.
        code: Course code.

    Returns:
        Course.

    Raises:
        HTTPException: 404 when the course is unknown.
    """
    with request.app.state.session_factory() as db:
        course = CourseRepository(db).get_course(code)
    if course is None:
        raise HTTPException(status_code=404, detail=f"找不到課程：{code}")
    return course


@note_schedule_router.get("", operation_id="get_note_schedule")
def get_note_schedule(request: Request) -> dict[str, Any]:
    """Return scheduled chapters, pause state, and the next Gemini quota resume time.

    Args:
        request: Incoming HTTP request.

    Returns:
        Schedule status.
    """
    return _scheduler(request).status()


@note_schedule_router.get("/candidates/{course_key}", operation_id="get_note_schedule_candidates")
def get_candidates(course_key: str, request: Request) -> dict[str, Any]:
    """List a course's lectures with whether a chapter note exists and whether it is scheduled.

    Args:
        course_key: Course code.
        request: Incoming HTTP request.

    Returns:
        `{"chapters": [{lecture_no, chapter_id, title, has_note, scheduled}]}`.
    """
    course = _course(request, course_key)
    pipeline = build_note_pipeline(request.app.state.config, request.app.state.session_factory)
    noted = {c["chapter_id"] for c in pipeline.list_chapters(course.code)}
    items = {
        i["chapter_id"]: i["status"]
        for i in _scheduler(request).status()["items"]
        if i["course_key"] == course.code
    }
    rows = []
    for lec in sorted(course.lectures, key=lambda lec: lec.no):
        cid = f"ch{lec.no:02d}"
        rows.append(
            {
                "lecture_no": lec.no,
                "chapter_id": cid,
                "title": lec.topic or lec.filename,
                "has_note": cid in noted,
                "scheduled": items.get(cid, ""),
            }
        )
    return {"chapters": rows}


@note_schedule_router.post("", operation_id="add_note_schedule")
def add_note_schedule(body: ScheduleRequest, request: Request) -> dict[str, int]:
    """Approve chapters: they will be generated in the background one by one.

    Args:
        body: Course and lecture numbers.
        request: Incoming HTTP request.

    Returns:
        `{"added", "skipped"}`.

    Raises:
        HTTPException: 422 when none of the lecture numbers exist.
    """
    course = _course(request, body.course_key)
    if not {lec.no for lec in course.lectures} & set(body.lecture_nos):
        raise HTTPException(status_code=422, detail="找不到指定的講次")
    return _scheduler(request).enqueue_course(course, body.lecture_nos)


@note_schedule_router.post("/pause", operation_id="pause_note_schedule")
def pause_note_schedule(request: Request) -> dict[str, Any]:
    """Pause the schedule (the running module finishes first).

    Args:
        request: Incoming HTTP request.

    Returns:
        Schedule status.
    """
    return _scheduler(request).pause()


@note_schedule_router.post("/resume", operation_id="resume_note_schedule")
def resume_note_schedule(request: Request) -> dict[str, Any]:
    """Resume the schedule.

    Args:
        request: Incoming HTTP request.

    Returns:
        Schedule status.
    """
    return _scheduler(request).resume()


@note_schedule_router.post("/clear-finished", operation_id="clear_note_schedule")
def clear_finished(request: Request) -> dict[str, int]:
    """Remove done and failed chapters from the list.

    Args:
        request: Incoming HTTP request.

    Returns:
        `{"removed": n}`.
    """
    return {"removed": _scheduler(request).clear_finished()}

"""HTTP routes for the learning aids: lecture PDF and key points, memory strength, and the tutor."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError, StudioError
from notebooklm_batch_studio.services.learning_service import LearningService

learning_router = APIRouter(prefix="/api/courses/{code}", tags=["Learning"])


class KeyPointsIn(BaseModel):
    """Generate a lecture's key points.

    Attributes:
        force: Ask Gemini Notebook again even when key points are saved.
    """

    force: bool = False


class TutorIn(BaseModel):
    """A message to the tutor.

    Attributes:
        lecture_no: Lecture number, or null for the whole course.
        message: The student's message.
    """

    lecture_no: int | None = None
    message: str = Field(..., min_length=1, max_length=2000)


def _learning(request: Request) -> LearningService:
    """Get the learning service from the app.

    Args:
        request: Incoming request.

    Returns:
        LearningService.
    """
    service: LearningService = request.app.state.learning
    return service


@learning_router.api_route(
    "/lectures/{lecture_no}/source.pdf", methods=["GET", "HEAD"], operation_id="get_lecture_pdf"
)
def get_lecture_pdf(code: str, lecture_no: int, request: Request) -> FileResponse:
    """Show the lecture's own PDF (read-only, straight from the course folder).

    Args:
        code: Course code.
        lecture_no: Lecture number.
        request: Incoming request.

    Returns:
        The PDF, displayed inline.

    Raises:
        HTTPException: 404 when the course, lecture or file is missing; 403 outside the course folder.
    """
    try:
        path = _learning(request).source_pdf(code, lecture_no)
    except (CourseNotFoundError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileResponse(
        path, media_type="application/pdf", content_disposition_type="inline", filename=path.name
    )


@learning_router.get("/lectures/{lecture_no}/key-points", operation_id="get_key_points")
def get_key_points(code: str, lecture_no: int, request: Request) -> dict[str, Any]:
    """Saved key points of a lecture (empty list when not generated yet).

    Args:
        code: Course code.
        lecture_no: Lecture number.
        request: Incoming request.

    Returns:
        {"points": [...], "created_at": ...}.

    Raises:
        HTTPException: 404 for an unknown course or lecture.
    """
    try:
        return _learning(request).key_points(code, lecture_no)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@learning_router.post("/lectures/{lecture_no}/key-points", operation_id="generate_key_points")
async def generate_key_points(
    code: str, lecture_no: int, req: KeyPointsIn, request: Request
) -> dict[str, Any]:
    """Ask Gemini Notebook for the key points once (saved and reused; `force` asks again).

    Args:
        code: Course code.
        lecture_no: Lecture number.
        req: Whether to ask again.
        request: Incoming request.

    Returns:
        Key points with `from_cache`.

    Raises:
        HTTPException: 404 unknown lecture, 422 not uploaded / unreadable answer, 502 Gemini Notebook error.
    """
    try:
        return await _learning(request).generate_key_points(code, lecture_no, req.force)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StudioError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@learning_router.get("/study/memory", operation_id="get_memory_strength")
def get_memory_strength(code: str, request: Request) -> dict[str, Any]:
    """Memory strength per lecture (forgetting curve), study streak and 4-week heatmap.

    Args:
        code: Course code.
        request: Incoming request.

    Returns:
        Memory overview.

    Raises:
        HTTPException: 404 for an unknown course.
    """
    try:
        return _learning(request).memory(code)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@learning_router.get("/study/tutor", operation_id="get_tutor_history")
def get_tutor_history(
    code: str, request: Request, lecture_no: int | None = Query(default=None)
) -> list[dict[str, Any]]:
    """The saved tutor conversation for a lecture (or the whole course).

    Args:
        code: Course code.
        request: Incoming request.
        lecture_no: Lecture number, or omitted for the whole course.

    Returns:
        Messages, oldest first.
    """
    return _learning(request).tutor_history(code, lecture_no)


@learning_router.post("/study/tutor", operation_id="ask_tutor")
async def ask_tutor(code: str, req: TutorIn, request: Request) -> dict[str, Any]:
    """Send a message to the Socratic tutor (uses Gemini Notebook; the reply is saved).

    Args:
        code: Course code.
        req: Lecture and message.
        request: Incoming request.

    Returns:
        The tutor's reply.

    Raises:
        HTTPException: 404 unknown course, 422 empty message / not uploaded, 502 Gemini Notebook error.
    """
    try:
        return await _learning(request).ask_tutor(code, req.lecture_no, req.message)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StudioError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@learning_router.delete("/study/tutor", operation_id="clear_tutor")
def clear_tutor(code: str, request: Request, lecture_no: int | None = Query(default=None)) -> dict[str, Any]:
    """Start the tutor conversation over (deletes the local copy only).

    Args:
        code: Course code.
        request: Incoming request.
        lecture_no: Lecture number, or omitted for the whole course.

    Returns:
        {"cleared": true}.
    """
    _learning(request).clear_tutor(code, lecture_no)
    return {"cleared": True}

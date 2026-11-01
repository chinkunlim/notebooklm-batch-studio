"""HTTP routes for the student's study plan, progress marks, spaced review and explanations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError, StudioError
from notebooklm_batch_studio.services.study_plan_service import StudyPlanService

plan_router = APIRouter(prefix="/api/courses/{code}/study", tags=["Study Plan"])


class ProgressIn(BaseModel):
    """Mark one reading / listening step.

    Attributes:
        lecture_no: Lecture number, or null for course-wide.
        step: 'audio' or 'guide'.
        done: True to mark done, false to undo.
    """

    lecture_no: int | None = Field(default=None)
    step: str = Field(..., description="'audio' or 'guide'")
    done: bool = Field(default=True)


class ReviewIn(BaseModel):
    """One spaced-review answer.

    Attributes:
        kind: 'flashcard' or 'mistake'.
        key: Stable item key.
        remembered: Whether the student recalled it.
        lecture_no: Lecture number.
        front: Prompt side.
        back: Answer side.
    """

    kind: str = Field(..., description="'flashcard' or 'mistake'")
    key: str = Field(..., description="Stable item key")
    remembered: bool
    lecture_no: int | None = None
    front: str = ""
    back: str = ""


class ExplainIn(BaseModel):
    """A quiz question to explain.

    Attributes:
        lecture_no: Lecture number, or null for course-wide questions.
        question: Question text.
        choices: Options in display order.
        answer_index: Index of the correct option.
        force: Ask NotebookLM again even when an explanation is saved.
    """

    lecture_no: int | None = None
    question: str
    choices: list[str]
    answer_index: int
    force: bool = False


def _plan(request: Request) -> StudyPlanService:
    """Get the study-plan service from the app.

    Args:
        request: Incoming request.

    Returns:
        StudyPlanService.
    """
    service: StudyPlanService = request.app.state.study_plan
    return service


@plan_router.get("/plan", operation_id="get_study_plan")
def get_study_plan(code: str, request: Request) -> dict[str, Any]:
    """Today's plan: next step, per-lecture progress, exam countdown, reviews due.

    Args:
        code: Course code.
        request: Incoming request.

    Returns:
        Study plan.

    Raises:
        HTTPException: 404 when the course does not exist.
    """
    try:
        return _plan(request).get_plan(code)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@plan_router.post("/progress", operation_id="mark_study_step")
def mark_study_step(code: str, req: ProgressIn, request: Request) -> dict[str, Any]:
    """Mark a listening / reading step done (quizzes and flashcards are tracked automatically).

    Args:
        code: Course code.
        req: Step to mark.
        request: Incoming request.

    Returns:
        The updated plan.

    Raises:
        HTTPException: 404 for an unknown course, 422 for a step that cannot be marked.
    """
    try:
        return _plan(request).mark_step(code, req.lecture_no, req.step, req.done)
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@plan_router.get("/reviews/due", operation_id="get_due_reviews")
def get_due_reviews(
    code: str, request: Request, lecture_no: int | None = Query(default=None)
) -> list[dict[str, Any]]:
    """Flashcards and mistakes due for review now.

    Args:
        code: Course code.
        request: Incoming request.
        lecture_no: Optional lecture filter.

    Returns:
        Due review items.
    """
    return _plan(request).due_reviews(code, lecture_no)


@plan_router.post("/reviews", operation_id="record_review")
def record_review(code: str, req: ReviewIn, request: Request) -> dict[str, Any]:
    """Record a review answer and schedule the next review (1, 3, 7, 14, 30 days).

    Args:
        code: Course code.
        req: Review answer.
        request: Incoming request.

    Returns:
        New stage and due time.

    Raises:
        HTTPException: 422 for an unknown kind.
    """
    try:
        return _plan(request).record_review(
            code, req.kind, req.key, req.remembered, req.lecture_no, req.front, req.back
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@plan_router.post("/explain", operation_id="explain_question")
async def explain_question(code: str, req: ExplainIn, request: Request) -> dict[str, Any]:
    """Ask NotebookLM why the answer is correct, grounded in the course's own sources.

    Args:
        code: Course code.
        req: Question, options and correct index.
        request: Incoming request.

    Returns:
        The explanation.

    Raises:
        HTTPException: 404 for an unknown course, 422 for bad input, 502 when NotebookLM fails.
    """
    try:
        return await _plan(request).explain(
            code, req.lecture_no, req.question, req.choices, req.answer_index, req.force
        )
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StudioError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@plan_router.get("/explanations", operation_id="get_saved_explanations")
def get_saved_explanations(
    code: str, request: Request, lecture_no: int | None = Query(default=None)
) -> list[dict[str, Any]]:
    """Saved NotebookLM explanations (shown again without spending quota).

    Args:
        code: Course code.
        request: Incoming request.
        lecture_no: Optional lecture filter.

    Returns:
        Saved explanations, newest first.
    """
    return _plan(request).list_explanations(code, lecture_no)

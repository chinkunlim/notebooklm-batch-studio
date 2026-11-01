"""HTTP router for the Student Study Portal: quiz attempts, weakness notebook, and Anki exports."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from notebooklm_batch_studio.services.study_service import StudyTrackerService

study_router = APIRouter(prefix="/api/courses/{code}/study", tags=["Study Portal"])


class QuizMistakeIn(BaseModel):
    """Payload schema for an individual wrong question submission."""

    question_text: str = Field(..., description="Text of the question")
    choices: list[str] = Field(..., description="All answer choices")
    correct_index: int = Field(..., description="0-based index of the correct answer")
    selected_index: int = Field(..., description="0-based index of student choice")
    explanation: str = Field(..., description="Academic rationale")
    confidence: str | None = Field(default=None, description="'sure', 'unsure' or 'guess' before answering")


class QuizAttemptIn(BaseModel):
    """Payload schema for submitting a student quiz attempt."""

    lecture_no: int | None = Field(default=None, description="Lecture number or None for course-wide")
    quiz_variant: str = Field(..., description="Quiz variant identifier (academic, concept, etc.)")
    score: int = Field(..., ge=0, description="Score achieved")
    total_questions: int = Field(..., ge=1, description="Total question count")
    mistakes: list[QuizMistakeIn] = Field(default_factory=list, description="List of mistaken questions")
    confidence: dict[str, int] | None = Field(
        default=None, description='Counts from confidence ratings, e.g. {"sure_wrong": 2, "guess_right": 3}'
    )


@study_router.post("/quiz-attempts", operation_id="record_quiz_attempt")
def record_quiz_attempt(
    code: str,
    payload: QuizAttemptIn,
    request: Request,
) -> dict[str, Any]:
    """Record a completed quiz attempt along with wrong answers.

    Args:
        code: Course identifier.
        payload: Quiz submission data.
        request: FastAPI HTTP request context.

    Returns:
        Confirmation dictionary with recorded attempt ID.
    """
    study_service: StudyTrackerService = request.app.state.study_service
    mistakes_dicts = [m.model_dump() for m in payload.mistakes]
    attempt = study_service.record_quiz_attempt(
        course_code=code,
        lecture_no=payload.lecture_no,
        quiz_variant=payload.quiz_variant,
        score=payload.score,
        total_questions=payload.total_questions,
        mistakes_data=mistakes_dicts,
        confidence_summary=payload.confidence,
    )
    return {
        "status": "ok",
        "attempt_id": attempt.id,
        "score": attempt.score,
        "total": attempt.total_questions,
    }


@study_router.get("/history", operation_id="get_study_history")
def get_study_history(
    code: str,
    request: Request,
    lecture_no: int | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Retrieve quiz attempt history for a course or lecture.

    Args:
        code: Course identifier.
        request: FastAPI HTTP request context.
        lecture_no: Optional lecture sequence number filter.

    Returns:
        List of attempt summary records.
    """
    study_service: StudyTrackerService = request.app.state.study_service
    attempts = study_service.get_study_history(code, lecture_no=lecture_no)
    return [
        {
            "id": a.id,
            "course_code": a.course_code,
            "lecture_no": a.lecture_no,
            "quiz_variant": a.quiz_variant,
            "score": a.score,
            "total_questions": a.total_questions,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in attempts
    ]


@study_router.get("/mistakes", operation_id="get_weaknesses")
def get_weaknesses(
    code: str,
    request: Request,
    lecture_no: int | None = Query(default=None),
    only_unresolved: bool = Query(default=True),
) -> list[dict[str, Any]]:
    """Retrieve mistaken questions stored in the student weakness notebook.

    Args:
        code: Course identifier.
        request: FastAPI HTTP request context.
        lecture_no: Optional lecture sequence number filter.
        only_unresolved: Whether to exclude already mastered mistakes.

    Returns:
        List of mistake records.
    """
    study_service: StudyTrackerService = request.app.state.study_service
    mistakes = study_service.get_weaknesses(code, lecture_no=lecture_no, only_unresolved=only_unresolved)
    return [
        {
            "id": m.id,
            "attempt_id": m.attempt_id,
            "course_code": m.course_code,
            "lecture_no": m.lecture_no,
            "question_text": m.question_text,
            "choices": m.choices,
            "correct_index": m.correct_index,
            "selected_index": m.selected_index,
            "explanation": m.explanation,
            "is_resolved": m.is_resolved,
            "confidence": m.confidence,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in mistakes
    ]


@study_router.post("/mistakes/{mistake_id}/resolve", operation_id="resolve_weakness")
def resolve_weakness(
    code: str,
    mistake_id: str,
    request: Request,
) -> dict[str, Any]:
    """Mark a weakness question as resolved after student re-practice.

    Args:
        code: Course identifier.
        mistake_id: Unique identifier of the mistake record.
        request: FastAPI HTTP request context.

    Returns:
        Success status dictionary.

    Raises:
        HTTPException: 404 if mistake is not found.
    """
    study_service: StudyTrackerService = request.app.state.study_service
    resolved = study_service.resolve_weakness(mistake_id)
    if not resolved:
        raise HTTPException(status_code=404, detail="Mistake record not found")
    return {"status": "ok", "resolved": True}


@study_router.get("/mistakes/anki.csv", operation_id="export_weaknesses_anki")
def export_weaknesses_anki(
    code: str,
    request: Request,
    lecture_no: int | None = Query(default=None),
) -> Response:
    """Download an Anki-compatible CSV deck containing student weaknesses.

    Args:
        code: Course identifier.
        request: FastAPI HTTP request context.
        lecture_no: Optional lecture sequence number filter.

    Returns:
        CSV file response configured for direct Anki import.
    """
    study_service: StudyTrackerService = request.app.state.study_service
    csv_content = study_service.export_weaknesses_to_anki_csv(code, lecture_no=lecture_no)
    suffix = f"L{lecture_no:02d}_" if lecture_no is not None else ""
    filename = f"{code}_{suffix}Weakness_Anki.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@study_router.get("/flashcards", operation_id="get_lecture_flashcards")
def get_lecture_flashcards(
    code: str,
    lecture_no: int,
    request: Request,
) -> dict[str, Any]:
    """Retrieve flashcards for in-browser 3D review.

    Args:
        code: Course identifier.
        lecture_no: Lecture sequence number.
        request: FastAPI HTTP request context.

    Returns:
        Dictionary with list of flashcards.
    """
    study_service: StudyTrackerService = request.app.state.study_service
    cards = study_service.get_lecture_flashcards(code, lecture_no=lecture_no)
    return {"status": "ok", "count": len(cards), "cards": cards}

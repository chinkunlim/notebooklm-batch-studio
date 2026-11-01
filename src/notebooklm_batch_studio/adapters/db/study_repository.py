"""Database repository for student quiz attempts and mistake tracking."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.models import (
    QuizAttemptRecord,
    QuizMistakeRecord,
)
from notebooklm_batch_studio.domain.models import (
    QuizAttempt,
    QuizMistake,
)

logger = logging.getLogger(__name__)


def _to_domain_mistake(record: QuizMistakeRecord) -> QuizMistake:
    """Convert an ORM QuizMistakeRecord to a pure domain QuizMistake entity.

    Args:
        record: Database quiz mistake record.

    Returns:
        Immutable domain QuizMistake entity.
    """
    choices: list[str] = []
    if record.choices_json:
        try:
            choices = json.loads(record.choices_json)
        except json.JSONDecodeError:
            choices = []

    return QuizMistake(
        id=record.id,
        attempt_id=record.attempt_id,
        course_code=record.course_code,
        lecture_no=record.lecture_no,
        question_text=record.question_text,
        choices=choices,
        correct_index=record.correct_index,
        selected_index=record.selected_index,
        explanation=record.explanation,
        is_resolved=record.is_resolved,
        created_at=record.created_at,
        confidence=record.confidence,
    )


def _to_domain_attempt(record: QuizAttemptRecord, mistakes: list[QuizMistake] | None = None) -> QuizAttempt:
    """Convert an ORM QuizAttemptRecord to a pure domain QuizAttempt entity.

    Args:
        record: Database quiz attempt record.
        mistakes: Optional list of associated mistake entities.

    Returns:
        Immutable domain QuizAttempt entity.
    """
    return QuizAttempt(
        id=record.id,
        course_code=record.course_code,
        lecture_no=record.lecture_no,
        quiz_variant=record.quiz_variant,
        score=record.score,
        total_questions=record.total_questions,
        created_at=record.created_at,
        mistakes=mistakes or [],
    )


class StudyRepository:
    """Database access for student quiz attempts and mistake records."""

    def __init__(self, session: Session) -> None:
        """Bind repository to an active SQLAlchemy database session.

        Args:
            session: Active SQLAlchemy session.
        """
        self.session = session

    def record_attempt(self, attempt: QuizAttempt) -> None:
        """Persist a completed quiz attempt along with any mistake records.

        Args:
            attempt: Domain QuizAttempt entity containing any mistakes.
        """
        attempt_rec = QuizAttemptRecord(
            id=attempt.id,
            course_code=attempt.course_code,
            lecture_no=attempt.lecture_no,
            quiz_variant=attempt.quiz_variant,
            score=attempt.score,
            total_questions=attempt.total_questions,
            confidence_json=(
                json.dumps(attempt.confidence_summary) if attempt.confidence_summary is not None else None
            ),
        )
        self.session.add(attempt_rec)

        for m in attempt.mistakes:
            mistake_rec = QuizMistakeRecord(
                id=m.id,
                attempt_id=attempt.id,
                course_code=attempt.course_code,
                lecture_no=attempt.lecture_no,
                question_text=m.question_text,
                choices_json=json.dumps(m.choices, ensure_ascii=False),
                correct_index=m.correct_index,
                selected_index=m.selected_index,
                explanation=m.explanation,
                is_resolved=m.is_resolved,
                confidence=m.confidence,
            )
            self.session.add(mistake_rec)
        self.session.commit()
        logger.info(
            "Persisted quiz attempt %s for course %s (score=%d/%d)",
            attempt.id,
            attempt.course_code,
            attempt.score,
            attempt.total_questions,
        )

    def list_attempts(self, course_code: str, lecture_no: int | None = None) -> list[QuizAttempt]:
        """List quiz attempts for a course or specific lecture.

        Args:
            course_code: Course identifier.
            lecture_no: Optional lecture sequence number filter.

        Returns:
            List of domain QuizAttempt entities ordered by timestamp descending.
        """
        stmt = select(QuizAttemptRecord).where(QuizAttemptRecord.course_code == course_code)
        if lecture_no is not None:
            stmt = stmt.where(QuizAttemptRecord.lecture_no == lecture_no)
        stmt = stmt.order_by(QuizAttemptRecord.created_at.desc())

        records = self.session.execute(stmt).scalars().all()
        return [_to_domain_attempt(r) for r in records]

    def list_mistakes(
        self,
        course_code: str,
        lecture_no: int | None = None,
        only_unresolved: bool = True,
    ) -> list[QuizMistake]:
        """List recorded mistakes for a course or specific lecture.

        Args:
            course_code: Course identifier.
            lecture_no: Optional lecture sequence number filter.
            only_unresolved: Whether to include only unresolved mistakes.

        Returns:
            List of domain QuizMistake entities.
        """
        stmt = select(QuizMistakeRecord).where(QuizMistakeRecord.course_code == course_code)
        if lecture_no is not None:
            stmt = stmt.where(QuizMistakeRecord.lecture_no == lecture_no)
        if only_unresolved:
            stmt = stmt.where(QuizMistakeRecord.is_resolved.is_(False))
        stmt = stmt.order_by(QuizMistakeRecord.created_at.desc())

        records = self.session.execute(stmt).scalars().all()
        return [_to_domain_mistake(r) for r in records]

    def resolve_mistake(self, mistake_id: str) -> bool:
        """Mark a quiz mistake as resolved.

        Args:
            mistake_id: UUID of the mistake record.

        Returns:
            True if updated, False if mistake record not found.
        """
        stmt = select(QuizMistakeRecord).where(QuizMistakeRecord.id == mistake_id)
        record = self.session.execute(stmt).scalar_one_or_none()
        if record is None:
            return False
        record.is_resolved = True
        self.session.commit()
        logger.info("Marked quiz mistake %s as resolved", mistake_id)
        return True

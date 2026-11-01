"""Database access for the learning aids: lecture key points, tutor conversations and study activity."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.models import (
    KeyPointsRecord,
    QuizAttemptRecord,
    ReviewItemRecord,
    StudyProgressRecord,
    TutorMessageRecord,
    utc_now,
)


def _aware(value: datetime | None) -> datetime | None:
    """Treat naive datetimes read back from SQLite as UTC.

    Args:
        value: Datetime or None.

    Returns:
        A timezone-aware datetime, or None.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=utc_now().tzinfo)


class LearningRepository:
    """Key points, tutor messages and activity timestamps for one session."""

    def __init__(self, session: Session) -> None:
        """Bind to a session.

        Args:
            session: SQLAlchemy session.
        """
        self.session = session

    def save_key_points(self, course_code: str, lecture_no: int, points: list[dict[str, Any]]) -> None:
        """Save (or replace) the key points of one lecture.

        Args:
            course_code: Course code.
            lecture_no: Lecture number.
            points: Key points ({quote, page, importance, note}).
        """
        item_id = f"{course_code}:{lecture_no}"
        record = self.session.get(KeyPointsRecord, item_id)
        if record is None:
            record = KeyPointsRecord(id=item_id, course_code=course_code, lecture_no=lecture_no)
            self.session.add(record)
        record.points_json = json.dumps(points, ensure_ascii=False)
        record.created_at = utc_now()
        self.session.flush()
        self.session.commit()

    def get_key_points(self, course_code: str, lecture_no: int) -> dict[str, Any] | None:
        """Load the saved key points of one lecture.

        Args:
            course_code: Course code.
            lecture_no: Lecture number.

        Returns:
            {"points": [...], "created_at": iso} or None when none are saved.
        """
        record = self.session.get(KeyPointsRecord, f"{course_code}:{lecture_no}")
        if record is None:
            return None
        return {
            "points": json.loads(record.points_json),
            "created_at": (_aware(record.created_at) or utc_now()).isoformat(),
        }

    def add_tutor_message(
        self, course_code: str, lecture_no: int | None, role: str, text: str, conversation_id: str | None
    ) -> None:
        """Append one message to a tutor conversation.

        Args:
            course_code: Course code.
            lecture_no: Lecture number, or None for the whole course.
            role: 'student' or 'tutor'.
            text: Message text.
            conversation_id: Gemini Notebook conversation id, if known.
        """
        self.session.add(
            TutorMessageRecord(
                id=str(uuid.uuid4()),
                course_code=course_code,
                lecture_no=lecture_no,
                role=role,
                text=text,
                conversation_id=conversation_id,
                created_at=utc_now(),
            )
        )
        self.session.flush()
        self.session.commit()

    def tutor_messages(self, course_code: str, lecture_no: int | None) -> list[dict[str, Any]]:
        """List a tutor conversation, oldest first.

        Args:
            course_code: Course code.
            lecture_no: Lecture number, or None for the whole course.

        Returns:
            Messages with role, text, conversation_id and created_at.
        """
        lecture_filter = (
            TutorMessageRecord.lecture_no.is_(None)
            if lecture_no is None
            else TutorMessageRecord.lecture_no == lecture_no
        )
        stmt = (
            select(TutorMessageRecord)
            .where(TutorMessageRecord.course_code == course_code, lecture_filter)
            .order_by(TutorMessageRecord.created_at)
        )
        return [
            {
                "role": r.role,
                "text": r.text,
                "conversation_id": r.conversation_id,
                "created_at": (_aware(r.created_at) or utc_now()).isoformat(),
            }
            for r in self.session.scalars(stmt)
        ]

    def clear_tutor(self, course_code: str, lecture_no: int | None) -> None:
        """Delete a tutor conversation (local copy only; Gemini Notebook is not touched).

        Args:
            course_code: Course code.
            lecture_no: Lecture number, or None for the whole course.
        """
        lecture_filter = (
            TutorMessageRecord.lecture_no.is_(None)
            if lecture_no is None
            else TutorMessageRecord.lecture_no == lecture_no
        )
        self.session.execute(
            delete(TutorMessageRecord).where(TutorMessageRecord.course_code == course_code, lecture_filter)
        )
        self.session.flush()
        self.session.commit()

    def activity_times(self, course_code: str) -> list[datetime]:
        """Every moment the student studied this course: quizzes, reviews, marked steps, tutor questions.

        Args:
            course_code: Course code.

        Returns:
            Timezone-aware datetimes (unsorted).
        """
        times: list[datetime | None] = []
        times += self.session.scalars(
            select(QuizAttemptRecord.created_at).where(QuizAttemptRecord.course_code == course_code)
        ).all()
        times += self.session.scalars(
            select(ReviewItemRecord.last_reviewed_at).where(ReviewItemRecord.course_code == course_code)
        ).all()
        times += self.session.scalars(
            select(StudyProgressRecord.done_at).where(StudyProgressRecord.course_code == course_code)
        ).all()
        times += self.session.scalars(
            select(TutorMessageRecord.created_at).where(
                TutorMessageRecord.course_code == course_code, TutorMessageRecord.role == "student"
            )
        ).all()
        return [t for t in (_aware(x) for x in times) if t is not None]

    def memory_signals(self, course_code: str) -> dict[int | None, dict[str, list[Any]]]:
        """Per-lecture inputs for the memory-strength estimate.

        Args:
            course_code: Course code.

        Returns:
            Lecture number to {"quizzes": [(when, fraction correct)], "cards": [(last reviewed, stage)]}.
        """
        out: dict[int | None, dict[str, list[Any]]] = {}
        attempts = self.session.scalars(
            select(QuizAttemptRecord).where(QuizAttemptRecord.course_code == course_code)
        )
        for a in attempts:
            bucket = out.setdefault(a.lecture_no, {"quizzes": [], "cards": []})
            if a.total_questions:
                bucket["quizzes"].append((_aware(a.created_at), a.score / a.total_questions))
        items = self.session.scalars(
            select(ReviewItemRecord).where(
                ReviewItemRecord.course_code == course_code, ReviewItemRecord.last_reviewed_at.is_not(None)
            )
        )
        for item in items:
            bucket = out.setdefault(item.lecture_no, {"quizzes": [], "cards": []})
            bucket["cards"].append((_aware(item.last_reviewed_at), item.stage))
        return out

    def delete_course(self, course_code: str) -> None:
        """Remove a course's key points and tutor messages.

        Args:
            course_code: Course code.
        """
        self.session.execute(delete(KeyPointsRecord).where(KeyPointsRecord.course_code == course_code))
        self.session.execute(delete(TutorMessageRecord).where(TutorMessageRecord.course_code == course_code))
        self.session.flush()
        self.session.commit()

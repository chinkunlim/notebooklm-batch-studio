"""Database access for study progress marks and spaced-review items."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.models import ReviewItemRecord, StudyProgressRecord, utc_now
from notebooklm_batch_studio.domain.study_plan import ReviewItem


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


def _to_item(record: ReviewItemRecord) -> ReviewItem:
    """Convert a review record to the domain object.

    Args:
        record: ORM record.

    Returns:
        ReviewItem.
    """
    return ReviewItem(
        id=record.id,
        course_code=record.course_code,
        lecture_no=record.lecture_no,
        kind=record.kind,
        item_key=record.item_key,
        front=record.front,
        back=record.back,
        stage=record.stage,
        due_at=_aware(record.due_at) or utc_now(),
        last_reviewed_at=_aware(record.last_reviewed_at),
    )


class ReviewRepository:
    """Study progress marks and spaced-review items for one session."""

    def __init__(self, session: Session) -> None:
        """Bind to a session.

        Args:
            session: SQLAlchemy session.
        """
        self.session = session

    def mark_step(self, course_code: str, lecture_no: int | None, step: str, done: bool) -> None:
        """Mark one study step done (or not done).

        Args:
            course_code: Course code.
            lecture_no: Lecture number, or None for course-wide.
            step: Step key.
            done: True to mark done, False to clear.
        """
        stmt = select(StudyProgressRecord).where(
            StudyProgressRecord.course_code == course_code,
            StudyProgressRecord.lecture_no.is_(None)
            if lecture_no is None
            else StudyProgressRecord.lecture_no == lecture_no,
            StudyProgressRecord.step == step,
        )
        existing = self.session.scalars(stmt).first()
        if done and existing is None:
            self.session.add(StudyProgressRecord(course_code=course_code, lecture_no=lecture_no, step=step))
        elif not done and existing is not None:
            self.session.delete(existing)
        self.session.flush()
        self.session.commit()

    def list_steps(self, course_code: str) -> set[tuple[int | None, str]]:
        """Return every (lecture_no, step) a course has marked done.

        Args:
            course_code: Course code.

        Returns:
            Set of (lecture number, step key).
        """
        stmt = select(StudyProgressRecord).where(StudyProgressRecord.course_code == course_code)
        return {(r.lecture_no, r.step) for r in self.session.scalars(stmt)}

    def get_item(self, item_id: str) -> ReviewItem | None:
        """Load one review item.

        Args:
            item_id: Review item id.

        Returns:
            The item, or None.
        """
        record = self.session.get(ReviewItemRecord, item_id)
        return _to_item(record) if record else None

    def save_item(self, item: ReviewItem) -> None:
        """Insert or update a review item.

        Args:
            item: Review item.
        """
        record = self.session.get(ReviewItemRecord, item.id)
        if record is None:
            record = ReviewItemRecord(id=item.id)
            self.session.add(record)
        record.course_code = item.course_code
        record.lecture_no = item.lecture_no
        record.kind = item.kind
        record.item_key = item.item_key
        record.front = item.front
        record.back = item.back
        record.stage = item.stage
        record.due_at = item.due_at
        record.last_reviewed_at = item.last_reviewed_at
        self.session.flush()
        self.session.commit()

    def due_items(self, course_code: str, now: datetime, lecture_no: int | None = None) -> list[ReviewItem]:
        """List items due for review, oldest due first.

        Args:
            course_code: Course code.
            now: Current time.
            lecture_no: Optional lecture filter.

        Returns:
            Due review items.
        """
        stmt = select(ReviewItemRecord).where(
            ReviewItemRecord.course_code == course_code, ReviewItemRecord.due_at <= now
        )
        if lecture_no is not None:
            stmt = stmt.where(ReviewItemRecord.lecture_no == lecture_no)
        return [_to_item(r) for r in self.session.scalars(stmt.order_by(ReviewItemRecord.due_at))]

    def reviewed_lectures(self, course_code: str, kind: str) -> set[int | None]:
        """Lectures that have at least one reviewed item of a kind.

        Args:
            course_code: Course code.
            kind: 'flashcard' or 'mistake'.

        Returns:
            Lecture numbers.
        """
        stmt = select(ReviewItemRecord.lecture_no).where(
            ReviewItemRecord.course_code == course_code,
            ReviewItemRecord.kind == kind,
            ReviewItemRecord.last_reviewed_at.is_not(None),
        )
        return set(self.session.scalars(stmt.distinct()))

    def count_due(self, course_code: str, now: datetime) -> dict[str, int]:
        """Count due items per kind.

        Args:
            course_code: Course code.
            now: Current time.

        Returns:
            Kind to number of due items.
        """
        stmt = (
            select(ReviewItemRecord.kind, func.count(ReviewItemRecord.id))
            .where(ReviewItemRecord.course_code == course_code, ReviewItemRecord.due_at <= now)
            .group_by(ReviewItemRecord.kind)
        )
        return {kind: int(n) for kind, n in self.session.execute(stmt)}

    def delete_course(self, course_code: str) -> None:
        """Remove a course's progress marks and review items.

        Args:
            course_code: Course code.
        """
        self.session.execute(
            delete(StudyProgressRecord).where(StudyProgressRecord.course_code == course_code)
        )
        self.session.execute(delete(ReviewItemRecord).where(ReviewItemRecord.course_code == course_code))
        self.session.flush()
        self.session.commit()

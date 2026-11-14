"""SQLAlchemy repository for Gemini Notebook Q&A notes (SPEC-011)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.models import CourseQANoteRecord
from notebooklm_batch_studio.domain.qa_notes import CourseQANote, QANoteRepositoryProtocol

logger = logging.getLogger(__name__)


class QANoteRepository(QANoteRepositoryProtocol):
    """Persist and query CourseQANote entities in SQLite."""

    def __init__(self, session: Session) -> None:
        """Bind repository to an active SQLAlchemy Session.

        Args:
            session: Active ORM database session.
        """
        self.session = session

    @staticmethod
    def _to_domain(rec: CourseQANoteRecord) -> CourseQANote:
        """Convert ORM record into domain CourseQANote.

        Args:
            rec: SQLAlchemy CourseQANoteRecord row.

        Returns:
            Populated CourseQANote dataclass instance.
        """
        try:
            tags = json.loads(rec.tags_json or "[]")
        except json.JSONDecodeError:
            tags = []
        return CourseQANote(
            id=rec.id,
            course_code=rec.course_code,
            lecture_no=rec.lecture_no,
            title=rec.title,
            content_markdown=rec.content_markdown,
            personal_memo=rec.personal_memo,
            tags=[str(t) for t in tags],
            source_scene=rec.source_scene,
            mastery_status=rec.mastery_status,
            is_uploaded_as_source=bool(rec.is_uploaded_as_source),
            uploaded_source_id=rec.uploaded_source_id,
            created_at=rec.created_at,
            updated_at=rec.updated_at,
        )

    @staticmethod
    def _create_record(note: CourseQANote, now: datetime) -> CourseQANoteRecord:
        """Build a new ORM CourseQANoteRecord from domain entity.

        Args:
            note: CourseQANote domain entity.
            now: Current UTC timestamp.

        Returns:
            New CourseQANoteRecord ready for session.add.
        """
        return CourseQANoteRecord(
            id=note.id,
            course_code=note.course_code,
            lecture_no=note.lecture_no,
            title=note.title,
            content_markdown=note.content_markdown,
            personal_memo=note.personal_memo,
            tags_json=json.dumps(note.tags, ensure_ascii=False),
            source_scene=note.source_scene,
            mastery_status=note.mastery_status,
            is_uploaded_as_source=note.is_uploaded_as_source,
            uploaded_source_id=note.uploaded_source_id,
            created_at=note.created_at or now,
            updated_at=now,
        )

    def upsert_note(self, note: CourseQANote) -> CourseQANote:
        """Insert or update a CourseQANote record.

        Args:
            note: CourseQANote domain entity to persist.

        Returns:
            Saved CourseQANote entity with synchronized timestamps.
        """
        now = datetime.now(UTC)
        rec = self.session.get(CourseQANoteRecord, note.id)
        if rec is None:
            rec = self._create_record(note, now)
            self.session.add(rec)
        else:
            rec.lecture_no = note.lecture_no
            rec.title = note.title
            rec.content_markdown = note.content_markdown
            rec.personal_memo = note.personal_memo
            rec.tags_json = json.dumps(note.tags, ensure_ascii=False)
            rec.source_scene = note.source_scene
            rec.mastery_status = note.mastery_status
            rec.is_uploaded_as_source = note.is_uploaded_as_source
            rec.uploaded_source_id = note.uploaded_source_id
            rec.updated_at = now
        self.session.commit()
        return self._to_domain(rec)

    def get_note(self, note_id: str) -> CourseQANote | None:
        """Retrieve one note by ID.

        Args:
            note_id: Note primary key.

        Returns:
            CourseQANote entity or None if not found.
        """
        rec = self.session.get(CourseQANoteRecord, note_id)
        return self._to_domain(rec) if rec is not None else None

    def list_notes(
        self,
        course_code: str | None = None,
        lecture_no: int | None = None,
        mastery_status: str | None = None,
    ) -> list[CourseQANote]:
        """List notes optionally filtered by course, lecture, or mastery status.

        Args:
            course_code: Optional course filter.
            lecture_no: Optional lecture sequence filter.
            mastery_status: Optional mastery filter (`needs_review` / `mastered`).

        Returns:
            List of matching CourseQANote entities ordered newest first.
        """
        stmt = select(CourseQANoteRecord)
        if course_code is not None:
            stmt = stmt.where(CourseQANoteRecord.course_code == course_code)
        if lecture_no is not None:
            stmt = stmt.where(CourseQANoteRecord.lecture_no == lecture_no)
        if mastery_status is not None:
            stmt = stmt.where(CourseQANoteRecord.mastery_status == mastery_status)
        stmt = stmt.order_by(CourseQANoteRecord.updated_at.desc())
        rows = self.session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in rows]

    def delete_note(self, note_id: str) -> bool:
        """Delete a note record from the database.

        Args:
            note_id: Note primary key.

        Returns:
            True if deleted, False if not found.
        """
        rec = self.session.get(CourseQANoteRecord, note_id)
        if rec is None:
            return False
        self.session.delete(rec)
        self.session.commit()
        return True

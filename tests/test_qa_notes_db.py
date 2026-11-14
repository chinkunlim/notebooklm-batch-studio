"""Tests for CourseQANote database records and persistence operations (SPEC-011)."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.models import CourseQANoteRecord, CourseRecord
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope


class TestCourseQANoteDB(unittest.TestCase):
    """Verify CourseQANoteRecord schema, defaults, constraints, and JSON fields."""

    def setUp(self) -> None:
        """Create in-memory SQLite database and tables."""
        self.engine = create_db_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session_ctx = session_scope(self.engine)
        self.session: Session = self.session_ctx.__enter__()

        # Insert reference course record
        course = CourseRecord(
            code="BIO101",
            name="細胞生物學",
            source_dir="/tmp/bio101",
            created_at=datetime.now(UTC),
        )
        self.session.add(course)
        self.session.commit()

    def tearDown(self) -> None:
        """Close session and dispose database."""
        self.session_ctx.__exit__(None, None, None)
        self.engine.dispose()

    def test_create_and_query_qa_note_record(self) -> None:
        """Verify saving a QA note with tags and querying with default mastery."""
        tags = ["課程/BIO101/L03", "L03", "類型/測驗追問", "掌握度/待加強", "主題/生物學/光反應"]
        note = CourseQANoteRecord(
            id="note-101",
            course_code="BIO101",
            lecture_no=3,
            title="光反應與能量傳遞",
            content_markdown="# 光反應與能量傳遞\n\n內容說明...",
            personal_memo="期末必考第3題",
            tags_json=json.dumps(tags, ensure_ascii=False),
            source_scene="quiz_explain",
            mastery_status="needs_review",
            is_uploaded_as_source=False,
            uploaded_source_id=None,
        )
        self.session.add(note)
        self.session.commit()

        queried = self.session.get(CourseQANoteRecord, "note-101")
        self.assertIsNotNone(queried)
        assert queried is not None
        self.assertEqual(queried.title, "光反應與能量傳遞")
        self.assertEqual(queried.mastery_status, "needs_review")
        self.assertFalse(queried.is_uploaded_as_source)
        self.assertEqual(json.loads(queried.tags_json), tags)

    def test_update_mastery_and_source_status(self) -> None:
        """Verify updating mastery status to mastered and recording uploaded source ID."""
        note = CourseQANoteRecord(
            id="note-102",
            course_code="BIO101",
            lecture_no=None,
            title="全課程核心心智圖說明",
            content_markdown="# 總覽",
            tags_json="[]",
            source_scene="chat_drawer",
        )
        self.session.add(note)
        self.session.commit()

        note.mastery_status = "mastered"
        note.is_uploaded_as_source = True
        note.uploaded_source_id = "src-rem-99"
        self.session.commit()

        refreshed = self.session.get(CourseQANoteRecord, "note-102")
        assert refreshed is not None
        self.assertEqual(refreshed.mastery_status, "mastered")
        self.assertTrue(refreshed.is_uploaded_as_source)
        self.assertEqual(refreshed.uploaded_source_id, "src-rem-99")


if __name__ == "__main__":
    unittest.main()

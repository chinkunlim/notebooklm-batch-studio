"""Tests for course status, course_no, record-only profile, and literature defaults (SPEC-014 §5.4)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.models import (
    CourseQANoteRecord,
    ExplanationRecord,
    KeyPointsRecord,
    LiteratureItemRecord,
    QuizAttemptRecord,
    QuizMistakeRecord,
    ReviewItemRecord,
    StudyProgressRecord,
    TutorMessageRecord,
)
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course, CourseStatus, Lecture, ProfileName
from notebooklm_batch_studio.domain.study_layout import DEFAULT_LAYOUT, CategoryRole
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.course_settings import CourseSettingsService
from notebooklm_batch_studio.services.job_planner import generate_jobs_for_course
from notebooklm_batch_studio.services.orchestrator import BatchStudioService


class CourseLifecycleDbTests(unittest.TestCase):
    """BDD scenarios for DB course status/course_no, record-only profile, and legacy literature alias."""

    def setUp(self) -> None:
        """Create an isolated SQLite database per test."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_url = f"sqlite:///{Path(self.tmpdir.name) / 'app.db'}"
        self.engine = create_db_engine(self.db_url)
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)

    def tearDown(self) -> None:
        """Dispose DB engine and clean up temporary folder."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_course_status_and_course_no_round_trip_and_filter(self) -> None:
        """Scenario 7a: status and course_no persist and list_courses filters by status."""
        with self.session_factory() as session:
            repo = CourseRepository(session)
            repo.save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir="/tmp/c1",
                    term="115-1",
                    subject="CP__30000-團體諮商",
                    course_no="CP30000",
                    status=CourseStatus.ACTIVE,
                )
            )
            repo.save_course(
                Course(
                    code="113-1_PSY101",
                    name="普通心理學",
                    source_dir="/tmp/c2",
                    term="113-1",
                    subject="PSY__101-普通心理學",
                    course_no="PSY101",
                    profile=ProfileName.RECORD_ONLY,
                    status=CourseStatus.ARCHIVED,
                )
            )

            loaded = repo.get_course("113-1_PSY101")
            assert loaded is not None
            self.assertEqual(loaded.status, CourseStatus.ARCHIVED)
            self.assertEqual(loaded.course_no, "PSY101")
            self.assertEqual(loaded.profile, ProfileName.RECORD_ONLY)

            archived = repo.list_courses(status=CourseStatus.ARCHIVED)
            self.assertEqual([c.code for c in archived], ["113-1_PSY101"])
            active = repo.list_courses(status=CourseStatus.ACTIVE)
            self.assertEqual([c.code for c in active], ["115-1_CP30000"])
            self.assertEqual(len(repo.list_courses()), 2)

    def test_record_only_profile_generates_no_jobs(self) -> None:
        """Scenario 7b: record-only courses produce zero scheduled artifact jobs."""
        course = Course(
            code="113-1_PSY101",
            name="普通心理學",
            source_dir="/tmp/c2",
            profile=ProfileName.RECORD_ONLY,
            lectures=[Lecture(no=1, topic="導論", filename="01.pdf", sha256="abc")],
        )
        self.assertEqual(generate_jobs_for_course(course), [])

    def test_legacy_literature_singular_category_maps_to_materials_role(self) -> None:
        """Scenario 7c: existing DB row with '01 Material' resolves to CategoryRole.MATERIALS."""
        with self.session_factory() as session:
            session.add(
                LiteratureItemRecord(
                    key="LegacyPaper_2022",
                    position=0,
                    input_text="10.1000/legacy",
                    target_category="01 Material",
                )
            )
            session.commit()

            item = LiteratureRepository(session).get_item("LegacyPaper_2022")
            assert item is not None
            self.assertEqual(item.target_category, "01 Material")
            self.assertEqual(DEFAULT_LAYOUT.role_of(item.target_category), CategoryRole.MATERIALS)


class CourseDeletionRulesTests(unittest.TestCase):
    """BDD scenarios for Google-Classroom-style archive-before-delete rules."""

    def setUp(self) -> None:
        """Create an isolated temporary environment and SQLite database."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmpdir.name) / "data"
        self.cfg = AppConfig(
            data_dir=self.data_dir,
            database_url=f"sqlite:///{self.data_dir / 'db' / 'app.db'}",
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
            log_to_file=False,
        )
        self.cfg.ensure_data_dirs()
        self.engine = create_db_engine(self.cfg.database_url)
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)

    def tearDown(self) -> None:
        """Dispose DB engine and clean up temporary workspace."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_delete_refused_unless_archived(self) -> None:
        """Active courses cannot be deleted via service, HTTP (409), or MCP (even confirm=True)."""
        study_dir = self.cfg.study_root_dir / "115-1" / "CP__30000-團體諮商"
        note_file = study_dir / "03 Notes" / "我的隨筆.md"
        note_file.parent.mkdir(parents=True, exist_ok=True)
        note_file.write_text("keep", encoding="utf-8")

        with self.session_factory() as session:
            c_repo = CourseRepository(session)
            q_repo = QueueRepository(session)
            c_repo.save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir=str(study_dir),
                    study_dir=str(study_dir),
                    status=CourseStatus.ACTIVE,
                    course_no="CP30000",
                    term="115-1",
                )
            )
            cs = CourseSettingsService(c_repo, q_repo, self.cfg)
            with self.assertRaisesRegex(ValueError, "封存"):
                cs.delete_course("115-1_CP30000")

            svc = BatchStudioService(c_repo, q_repo, mock.MagicMock(), self.cfg)
            http = TestClient(create_app(config=self.cfg, service=svc, study_service=mock.MagicMock()))
            resp = http.delete("/api/courses/115-1_CP30000")
            self.assertEqual(resp.status_code, 409)
            self.assertIn("封存", resp.json()["detail"])

            mcp = build_mcp_server(service=svc, study_service=mock.MagicMock(), config=self.cfg)
            tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
            mcp_res = json.loads(tools["delete_course"].fn("115-1_CP30000", confirm=True))
            self.assertFalse(mcp_res["confirmed"])
            self.assertIn("封存", mcp_res["warning"])

            self.assertIsNotNone(c_repo.get_course("115-1_CP30000"))
            self.assertTrue(note_file.is_file())

    def test_delete_archived_course_keeps_study_files(self) -> None:
        """Deleting an archived course removes DB rows only and leaves all study/ files untouched."""
        study_dir = self.cfg.study_root_dir / "115-1" / "CP__30000-團體諮商"
        nlm_guide = study_dir / "03 Notes" / "NotebookLM" / "01_x" / "study_guide.md"
        user_note = study_dir / "03 Notes" / "我的隨筆.md"
        nlm_guide.parent.mkdir(parents=True, exist_ok=True)
        nlm_guide.write_text("# guide", encoding="utf-8")
        user_note.write_text("# personal", encoding="utf-8")

        with self.session_factory() as session:
            c_repo = CourseRepository(session)
            q_repo = QueueRepository(session)
            c_repo.save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir=str(study_dir),
                    study_dir=str(study_dir),
                    status=CourseStatus.ARCHIVED,
                    course_no="CP30000",
                    term="115-1",
                )
            )
            session.add_all(
                [
                    QuizAttemptRecord(
                        id="qa-1",
                        course_code="115-1_CP30000",
                        lecture_no=1,
                        quiz_variant="quiz_1",
                        score=8,
                        total_questions=10,
                    ),
                    QuizMistakeRecord(
                        id="qm-1",
                        attempt_id="qa-1",
                        course_code="115-1_CP30000",
                        lecture_no=1,
                        question_text="Q?",
                        choices_json='["A","B"]',
                        correct_index=0,
                        selected_index=1,
                        explanation="Because A.",
                    ),
                    StudyProgressRecord(course_code="115-1_CP30000", lecture_no=1, step="audio"),
                    ReviewItemRecord(
                        id="ri-1",
                        course_code="115-1_CP30000",
                        kind="flashcard",
                        item_key="k1",
                        due_at=datetime.now(UTC),
                    ),
                    ExplanationRecord(
                        id="115-1_CP30000:qk1",
                        course_code="115-1_CP30000",
                        question_key="qk1",
                        question="Q?",
                        answer_md="A",
                    ),
                    KeyPointsRecord(
                        id="115-1_CP30000:1", course_code="115-1_CP30000", lecture_no=1, points_json="[]"
                    ),
                    TutorMessageRecord(
                        id="tm-1", course_code="115-1_CP30000", lecture_no=1, role="student", text="hi"
                    ),
                    CourseQANoteRecord(
                        id="cn-1", course_code="115-1_CP30000", title="t", content_markdown="md"
                    ),
                ]
            )
            session.commit()

            result = CourseSettingsService(c_repo, q_repo, self.cfg).delete_course("115-1_CP30000")
            self.assertIsNone(c_repo.get_course("115-1_CP30000"))
            self.assertTrue(nlm_guide.is_file())
            self.assertTrue(user_note.is_file())
            self.assertEqual(
                result["learning_records_removed"],
                {
                    "quiz_attempts": 1,
                    "quiz_mistakes": 1,
                    "study_progress": 1,
                    "review_items": 1,
                    "explanations": 1,
                    "key_points": 1,
                    "tutor_messages": 1,
                    "course_qa_notes": 1,
                },
            )

    def test_delete_archived_course_moves_only_legacy_output(self) -> None:
        """Archived course deletion moves legacy output/courses/<code> to deleted/, keeping study/."""
        study_dir = self.cfg.study_root_dir / "115-1" / "CP__30000-團體諮商"
        study_file = study_dir / "03 Notes" / "NotebookLM" / "01_x" / "notes.md"
        study_file.parent.mkdir(parents=True, exist_ok=True)
        study_file.write_text("# stay", encoding="utf-8")

        legacy_out = self.cfg.courses_output_dir / "115-1_CP30000" / "01_x"
        legacy_out.mkdir(parents=True, exist_ok=True)
        (legacy_out / "quiz.json").write_text("{}", encoding="utf-8")

        with self.session_factory() as session:
            c_repo = CourseRepository(session)
            q_repo = QueueRepository(session)
            c_repo.save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir=str(study_dir),
                    study_dir=str(study_dir),
                    status=CourseStatus.ARCHIVED,
                    course_no="CP30000",
                    term="115-1",
                )
            )
            result = CourseSettingsService(c_repo, q_repo, self.cfg).delete_course("115-1_CP30000")
            self.assertTrue(study_file.is_file())
            self.assertFalse((self.cfg.courses_output_dir / "115-1_CP30000").exists())
            self.assertIsNotNone(result["moved_to"])
            self.assertTrue((Path(result["moved_to"]) / "115-1_CP30000" / "01_x" / "quiz.json").is_file())


if __name__ == "__main__":
    unittest.main()

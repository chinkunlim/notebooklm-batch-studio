"""Tests for cross-term LearningRecordService (SPEC-014 §5.6 Task 12)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.learning_repository import LearningRepository
from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.models import (
    CourseQANoteRecord,
    LiteratureItemRecord,
    QuizAttemptRecord,
    QuizMistakeRecord,
    ReviewItemRecord,
    StudyProgressRecord,
)
from notebooklm_batch_studio.adapters.db.notes_repository import QANoteRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    CourseStatus,
    JobStatus,
    Lecture,
)
from notebooklm_batch_studio.services.learning_record import LearningRecordService, RecordRepos


class LearningRecordServiceTests(unittest.TestCase):
    """BDD Scenario 12: multi-term learning record views, safety, stats, and Markdown/PDF export."""

    def setUp(self) -> None:
        """Create isolated DATA_DIR, SQLite DB, and temp external folder for symlink checks."""
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        data_dir = root / "data"
        self.outside_dir = root / "outside_secret"
        self.outside_dir.mkdir(parents=True, exist_ok=True)
        (self.outside_dir / "secret.txt").write_text("do not leak", encoding="utf-8")

        self.cfg = AppConfig(data_dir=data_dir, database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}")
        self.cfg.ensure_data_dirs()
        self.engine = create_db_engine(self.cfg.database_url)
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)

    def tearDown(self) -> None:
        """Dispose DB engine and temporary workspace."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _service(self, session: object) -> LearningRecordService:
        """Construct LearningRecordService backed by concrete SQLite repositories."""
        from sqlalchemy.orm import Session

        assert isinstance(session, Session)
        repos = RecordRepos(
            queue_repo=QueueRepository(session),
            study_repo=StudyRepository(session),
            learning_repo=LearningRepository(session),
            qa_repo=QANoteRepository(session),
            literature_repo=LiteratureRepository(session),
        )
        return LearningRecordService(self.cfg, CourseRepository(session), repos)

    def test_build_orders_terms_includes_archived_and_unregistered_skips_symlinks_and_computes_stats(
        self,
    ) -> None:
        """Build orders terms, includes archived/unregistered, skips symlinks, and computes stats."""
        now = datetime.now(UTC)
        # Active 115-1 registered course with files, stats, and artifacts
        c115_dir = self.cfg.study_root_dir / "115-1" / "CP__30000-團體諮商"
        (c115_dir / "01 Materials").mkdir(parents=True, exist_ok=True)
        (c115_dir / "01 Materials" / "paper.pdf").write_bytes(b"%PDF")
        (c115_dir / "02 Handouts").mkdir(parents=True, exist_ok=True)
        (c115_dir / "02 Handouts" / "slides.pptx").write_bytes(b"pptx-placeholder")
        (c115_dir / "03 Notes" / "NoteStudio").mkdir(parents=True, exist_ok=True)
        (c115_dir / "03 Notes" / "NoteStudio" / "ch01.md").write_text("# ch01", encoding="utf-8")
        (c115_dir / "05 Assignments" / "期中").mkdir(parents=True, exist_ok=True)
        (c115_dir / "05 Assignments" / "期中" / "報告.pdf").write_bytes(b"%PDF")
        # Hidden file and symlink outside DATA_DIR must both be ignored.
        (c115_dir / "02 Handouts" / ".DS_Store").write_text("junk", encoding="utf-8")
        (c115_dir / "02 Handouts" / "escape_link.txt").symlink_to(self.outside_dir / "secret.txt")
        (c115_dir / "01 Materials" / "link_dir").symlink_to(self.outside_dir)

        # Unregistered school-formatted folder in 115-1 + loose other folder
        unreg_dir = self.cfg.study_root_dir / "115-1" / "CP__31000-生涯諮商"
        (unreg_dir / "02 Handouts").mkdir(parents=True, exist_ok=True)
        (unreg_dir / "02 Handouts" / "week1.pdf").write_bytes(b"%PDF")
        (self.cfg.study_root_dir / "115-1" / "社團活動").mkdir(parents=True, exist_ok=True)

        # Archived 114-2 course
        c114_dir = self.cfg.study_root_dir / "114-2" / "CP__20100-發展心理學"
        (c114_dir / "01 Materials").mkdir(parents=True, exist_ok=True)
        (c114_dir / "01 Materials" / "ch01.pdf").write_bytes(b"%PDF")

        with self.session_factory() as session:
            c_repo, q_repo = CourseRepository(session), QueueRepository(session)
            c_repo.save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir=str(c115_dir),
                    study_dir=str(c115_dir),
                    term="115-1",
                    course_no="CP30000",
                    status=CourseStatus.ACTIVE,
                    lectures=[Lecture(no=1, topic="Ch1", filename="01.pdf", sha256="s1")],
                )
            )
            c_repo.save_course(
                Course(
                    code="114-2_CP20100",
                    name="發展心理學",
                    source_dir=str(c114_dir),
                    study_dir=str(c114_dir),
                    term="114-2",
                    course_no="CP20100",
                    status=CourseStatus.ARCHIVED,
                )
            )
            q_repo.enqueue_jobs(
                [
                    ArtifactJob(
                        id="j1",
                        course_code="115-1_CP30000",
                        lecture_no=1,
                        artifact_type=ArtifactType.AUDIO,
                        status=JobStatus.DONE,
                        output_file=str(c115_dir / "03 Notes" / "NotebookLM" / "01_ch1" / "audio.m4a"),
                    )
                ]
            )
            session.add_all(
                [
                    QuizAttemptRecord(
                        id="qa1",
                        course_code="115-1_CP30000",
                        lecture_no=1,
                        quiz_variant="quiz_1",
                        score=9,
                        total_questions=10,
                        created_at=now - timedelta(hours=2),
                    ),
                    QuizMistakeRecord(
                        id="qm1",
                        attempt_id="qa1",
                        course_code="115-1_CP30000",
                        lecture_no=1,
                        question_text="Q?",
                        choices_json='["A","B"]',
                        correct_index=0,
                        selected_index=1,
                        explanation="Exp",
                        is_resolved=False,
                    ),
                    StudyProgressRecord(
                        course_code="115-1_CP30000",
                        lecture_no=1,
                        step="audio",
                        done_at=now - timedelta(days=1),
                    ),
                    ReviewItemRecord(
                        id="flashcard:115-1_CP30000:k1",
                        course_code="115-1_CP30000",
                        lecture_no=1,
                        kind="flashcard",
                        item_key="k1",
                        stage=2,
                        due_at=now + timedelta(days=3),
                        last_reviewed_at=now - timedelta(minutes=30),
                    ),
                    CourseQANoteRecord(
                        id="n1", course_code="115-1_CP30000", title="T", content_markdown="Body"
                    ),
                    LiteratureItemRecord(key="lit1", input_text="DOI:1", course_code="115-1_CP30000"),
                ]
            )
            session.commit()

            # Ensure study files are listed without reading file contents!
            svc = self._service(session)
            with mock.patch("pathlib.Path.read_text", wraps=Path.read_text) as spy_read:
                terms = svc.build()
                read_paths = [str(call.args[0]) for call in spy_read.call_args_list if call.args]
                self.assertFalse(
                    any("secret.txt" in p or "slides.pptx" in p or "報告.pdf" in p for p in read_paths)
                )

            self.assertEqual([t.term for t in terms], ["114-2", "115-1"])
            archived_view = terms[0].courses[0]
            self.assertEqual(archived_view.status, "archived")
            self.assertEqual(archived_view.code, "114-2_CP20100")

            t115 = terms[1]
            self.assertIn("社團活動", t115.others)
            by_code = {c.code: c for c in t115.courses}
            self.assertIn("115-1_CP31000", by_code)
            self.assertEqual(by_code["115-1_CP31000"].status, "unregistered")

            main_course = by_code["115-1_CP30000"]
            self.assertEqual(main_course.status, "active")
            all_files = [f for cat in main_course.categories for f in cat.files]
            self.assertIn("02 Handouts/slides.pptx", all_files)
            self.assertIn("05 Assignments/期中/報告.pdf", all_files)
            self.assertNotIn("02 Handouts/.DS_Store", all_files)
            self.assertFalse(any("escape_link" in f or "secret" in f for f in all_files))

            expected_keys = {
                "lectures",
                "artifacts_done",
                "quiz_attempts",
                "quiz_best_score",
                "mistakes_open",
                "qa_notes",
                "literature",
                "notestudio_notes",
                "study_days",
                "study_minutes",
                "memory_strength_avg",
            }
            self.assertEqual(set(main_course.stats.keys()), expected_keys)
            self.assertEqual(main_course.stats["lectures"], 1)
            self.assertEqual(main_course.stats["artifacts_done"], 1)
            self.assertEqual(main_course.stats["quiz_attempts"], 1)
            self.assertEqual(main_course.stats["quiz_best_score"], 90)
            self.assertEqual(main_course.stats["mistakes_open"], 1)
            self.assertEqual(main_course.stats["qa_notes"], 1)
            self.assertEqual(main_course.stats["literature"], 1)
            self.assertEqual(main_course.stats["notestudio_notes"], 1)
            self.assertGreaterEqual(main_course.stats["study_days"], 1)
            self.assertGreater(main_course.stats["study_minutes"], 0)
            self.assertGreater(main_course.stats["memory_strength_avg"], 0)
            self.assertEqual(len(main_course.artifacts), 1)
            self.assertEqual(main_course.artifacts[0]["artifact_type"], "audio")

    def test_export_markdown_and_pdf_render_valid_outputs(self) -> None:
        """export_markdown contains expected headings; export_pdf writes valid PDF header."""
        c115_dir = self.cfg.study_root_dir / "115-1" / "CP__30000-團體諮商"
        (c115_dir / "02 Handouts").mkdir(parents=True, exist_ok=True)
        (c115_dir / "02 Handouts" / "slides.pptx").write_bytes(b"pptx")
        with self.session_factory() as session:
            c_repo = CourseRepository(session)
            c_repo.save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir=str(c115_dir),
                    study_dir=str(c115_dir),
                    term="115-1",
                    course_no="CP30000",
                )
            )
            svc = self._service(session)
            md = svc.export_markdown()
            self.assertTrue(md.startswith("# 學習紀錄"))
            self.assertIn("## 115-1", md)
            self.assertIn("### CP30000 團體諮商", md)
            self.assertIn("02 Handouts/slides.pptx", md)

            pdf_out = Path(self.tmpdir.name) / "record.pdf"
            written = svc.export_pdf(None, pdf_out)
            self.assertEqual(written, pdf_out)
            self.assertTrue(pdf_out.read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()

"""Tests for course status, course_no, record-only profile, and literature defaults (SPEC-014 §5.4)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.course_identity_repo import CourseIdentityRepository
from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.models import (
    ArtifactJobRecord,
    CourseQANoteRecord,
    ExplanationRecord,
    KeyPointsRecord,
    LectureRecord,
    LiteratureItemRecord,
    QuizAttemptRecord,
    QuizMistakeRecord,
    ReviewItemRecord,
    StudyProgressRecord,
    TutorMessageRecord,
    UiPreferenceRecord,
)
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.review_repository import ReviewRepository
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
    ProfileName,
)
from notebooklm_batch_studio.domain.study_layout import DEFAULT_LAYOUT, CategoryRole
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.course_lifecycle import CourseLifecycleService
from notebooklm_batch_studio.services.course_settings import CourseSettingsService
from notebooklm_batch_studio.services.job_planner import generate_jobs_for_course
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.study_plan_service import StudyPlanDeps, StudyPlanService


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


class CourseArchiveAndRenameTests(unittest.TestCase):
    """BDD Scenario 11a/11d-11g: archive queue/Today filtering and safe course-code rename."""

    def setUp(self) -> None:
        """Create isolated DATA_DIR and SQLite database for lifecycle tests."""
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        data_dir = root / "data"
        self.cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        self.cfg.ensure_data_dirs()
        self.engine = create_db_engine(self.cfg.database_url)
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)

    def tearDown(self) -> None:
        """Dispose DB engine and clean up temporary workspace."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _seed_full_course(self, session: object, code: str = "115-1") -> Path:
        """Populate all 11 child tables, UI preferences, and 5 local file types for rename tests."""
        from sqlalchemy.orm import Session

        assert isinstance(session, Session)
        study_dir = self.cfg.study_root_dir / "115-1" / "生涯諮商"
        qa_dir = study_dir / "03 Notes" / "QA_Notes"
        qa_dir.mkdir(parents=True, exist_ok=True)
        (study_dir / "02 Handouts").mkdir(parents=True, exist_ok=True)

        c_repo = CourseRepository(session)
        c_repo.save_course(
            Course(
                code=code,
                name="生涯諮商",
                source_dir=str(study_dir),
                study_dir=str(study_dir),
                notebook_id="nb-keep",
                term="115-1",
                lectures=[Lecture(no=1, topic="Intro", filename="01.pdf", sha256="sha1")],
            )
        )
        session.add_all(
            [
                ArtifactJobRecord(
                    id="job-1", course_code=code, lecture_no=1, artifact_type="audio", status="done"
                ),
                QuizAttemptRecord(
                    id="qa-1",
                    course_code=code,
                    lecture_no=1,
                    quiz_variant="quiz_1",
                    score=9,
                    total_questions=10,
                ),
                QuizMistakeRecord(
                    id="qm-1",
                    attempt_id="qa-1",
                    course_code=code,
                    lecture_no=1,
                    question_text="Q?",
                    choices_json='["A","B"]',
                    correct_index=0,
                    selected_index=1,
                    explanation="Exp",
                ),
                StudyProgressRecord(course_code=code, lecture_no=1, step="audio"),
                ReviewItemRecord(
                    id=f"flashcard:{code}:k1",
                    course_code=code,
                    kind="flashcard",
                    item_key="k1",
                    due_at=datetime.now(UTC),
                ),
                ExplanationRecord(
                    id=f"{code}:qk1", course_code=code, question_key="qk1", question="Q?", answer_md="A"
                ),
                KeyPointsRecord(id=f"{code}:1", course_code=code, lecture_no=1, points_json="[]"),
                TutorMessageRecord(id="tm-1", course_code=code, lecture_no=1, role="student", text="hi"),
                CourseQANoteRecord(id="cn-1", course_code=code, title="Note", content_markdown="Body"),
                LiteratureItemRecord(key="lit-1", input_text="Paper", course_code=code),
                UiPreferenceRecord(key="course", value=code),
                UiPreferenceRecord(key=f"place:{code}", value='{"step":"s-read"}'),
                UiPreferenceRecord(key=f"examNotice:{code}", value="2026-12-01"),
                UiPreferenceRecord(key=f"audio:{code}:1", value="12"),
                UiPreferenceRecord(key="palette", value="ink"),
            ]
        )
        session.commit()

        (study_dir / "course.toml").write_text(f'name = "生涯諮商"\ncode = "{code}"\n', encoding="utf-8")
        self.cfg.notes_state_dir.mkdir(parents=True, exist_ok=True)
        (self.cfg.notes_state_dir / f"{code}.json").write_text(
            json.dumps({"course_key": code, "chapters": {}}, ensure_ascii=False), encoding="utf-8"
        )
        (self.cfg.notes_state_dir / f"{code}.pause.json").write_text(
            json.dumps({"course_key": code, "paused": True}, ensure_ascii=False), encoding="utf-8"
        )
        scratch_dir = self.cfg.scratch_kind_dir("notes") / code
        scratch_dir.mkdir(parents=True, exist_ok=True)
        (scratch_dir / "draft.md").write_text("# draft", encoding="utf-8")
        (qa_dir / "cn-1_Note.md").write_text(
            f'---\nid: "cn-1"\ncourse: "{code}"\n---\n\ncourse: "{code}" in body stays untouched\n',
            encoding="utf-8",
        )
        (qa_dir / "cn-2_Legacy.md").write_text(
            f'---\nid: "cn-2"\ncourse_code: {code}\n---\n\nBody text.\n',
            encoding="utf-8",
        )
        return study_dir

    def test_archive_excludes_queue_today_and_due_reviews_and_restore_reinstates(self) -> None:
        """Scenario 11a: archived course is excluded from queue, Today, and due reviews until restored."""
        now = datetime.now(UTC)
        with self.session_factory() as session:
            c_repo, q_repo = CourseRepository(session), QueueRepository(session)
            s_repo, r_repo = StudyRepository(session), ReviewRepository(session)
            c_repo.save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir="/tmp/c1",
                    term="115-1",
                    course_no="CP30000",
                    lectures=[Lecture(no=1, topic="Ch1", filename="01.pdf", sha256="abc")],
                )
            )
            q_repo.enqueue_jobs(
                [
                    ArtifactJob(
                        id="j-pend",
                        course_code="115-1_CP30000",
                        lecture_no=1,
                        artifact_type=ArtifactType.AUDIO,
                    )
                ]
            )
            plan = StudyPlanService(StudyPlanDeps(c_repo, q_repo, s_repo, r_repo, mock.MagicMock()))
            plan.record_review(
                "115-1_CP30000", "flashcard", "k1", remembered=False, front="Q", back="A", now=now
            )
            due_now = now + timedelta(minutes=11)

            lifecycle = CourseLifecycleService(c_repo, q_repo, CourseIdentityRepository(session), self.cfg)
            self.assertIn("115-1_CP30000", [c["code"] for c in plan.get_today(now=due_now)])
            self.assertEqual(len(plan.due_reviews("115-1_CP30000", now=due_now)), 1)

            res_arch = lifecycle.archive("115-1_CP30000")
            self.assertEqual(res_arch["status"], "archived")
            self.assertIsNone(q_repo.claim_next_job("w1"))
            self.assertEqual(q_repo.count_by_status(runnable_only=True)[JobStatus.PENDING], 0)
            self.assertEqual([c["code"] for c in plan.get_today(now=due_now)], [])
            self.assertEqual(plan.due_reviews("115-1_CP30000", now=due_now), [])

            res_rest = lifecycle.restore("115-1_CP30000")
            self.assertEqual(res_rest["status"], "active")
            self.assertIn("115-1_CP30000", [c["code"] for c in plan.get_today(now=due_now)])
            self.assertEqual(len(plan.due_reviews("115-1_CP30000", now=due_now)), 1)
            claimed = q_repo.claim_next_job("w1")
            self.assertIsNotNone(claimed)
            assert claimed is not None
            self.assertEqual(claimed.course_code, "115-1_CP30000")

    def test_rename_dry_run_reports_counts_without_changes(self) -> None:
        """Scenario 11d: rename defaults to dry_run=True and mutates neither DB nor files."""
        with self.session_factory() as session:
            study_dir = self._seed_full_course(session, "115-1")
            c_repo, q_repo = CourseRepository(session), QueueRepository(session)
            lifecycle = CourseLifecycleService(c_repo, q_repo, CourseIdentityRepository(session), self.cfg)
            preview = lifecycle.rename("115-1", "115-1_CP31000")

            self.assertTrue(preview["dry_run"])
            self.assertEqual(preview["tables"]["lectures"], 1)
            self.assertEqual(preview["tables"]["course_qa_notes"], 1)
            self.assertEqual(preview["tables"]["ui_preferences"], 4)
            self.assertGreaterEqual(preview["files"]["qa_notes"], 2)
            self.assertIsNotNone(c_repo.get_course("115-1"))
            self.assertIsNone(c_repo.get_course("115-1_CP31000"))
            self.assertIn('code = "115-1"', (study_dir / "course.toml").read_text(encoding="utf-8"))
            self.assertTrue((self.cfg.notes_state_dir / "115-1.json").is_file())
            self.assertFalse((self.cfg.notes_state_dir / "115-1_CP31000.json").exists())

    def test_rename_refused_on_running_job_or_existing_target(self) -> None:
        """Scenario 11e: running jobs or colliding target code refuse rename with zero side effects."""
        with self.session_factory() as session:
            study_dir = self._seed_full_course(session, "115-1")
            c_repo, q_repo = CourseRepository(session), QueueRepository(session)
            lifecycle = CourseLifecycleService(c_repo, q_repo, CourseIdentityRepository(session), self.cfg)

            session.add(
                ArtifactJobRecord(id="j-run", course_code="115-1", artifact_type="quiz_1", status="running")
            )
            session.commit()
            with self.assertRaises(ValueError):
                lifecycle.rename("115-1", "115-1_CP31000", dry_run=False)
            self.assertIsNotNone(c_repo.get_course("115-1"))
            self.assertIn('code = "115-1"', (study_dir / "course.toml").read_text(encoding="utf-8"))

            session.query(ArtifactJobRecord).filter_by(id="j-run").delete()
            c_repo.save_course(Course(code="115-1_CP31000", name="已存在", source_dir="/tmp/existing"))
            with self.assertRaises(ValueError):
                lifecycle.rename("115-1", "115-1_CP31000", dry_run=False)
            self.assertIsNotNone(c_repo.get_course("115-1"))

    def test_rename_apply_updates_all_11_tables_prefs_and_files(self) -> None:
        """Scenario 11f: dry_run=False updates 11 child tables, prefs, 5 file types, and term/course_no."""
        with self.session_factory() as session:
            study_dir = self._seed_full_course(session, "115-1")
            c_repo, q_repo = CourseRepository(session), QueueRepository(session)
            lifecycle = CourseLifecycleService(c_repo, q_repo, CourseIdentityRepository(session), self.cfg)
            result = lifecycle.rename("115-1", "115-1_CP31000", dry_run=False)

            self.assertFalse(result["dry_run"])
            self.assertIsNone(c_repo.get_course("115-1"))
            new_course = c_repo.get_course("115-1_CP31000")
            assert new_course is not None
            self.assertEqual(new_course.term, "115-1")
            self.assertEqual(new_course.course_no, "CP31000")
            self.assertEqual(new_course.notebook_id, "nb-keep")
            self.assertEqual(new_course.study_dir, str(study_dir))
            self.assertTrue(study_dir.is_dir())

            for model in (
                LectureRecord,
                ArtifactJobRecord,
                QuizAttemptRecord,
                QuizMistakeRecord,
                StudyProgressRecord,
                ReviewItemRecord,
                ExplanationRecord,
                KeyPointsRecord,
                TutorMessageRecord,
                CourseQANoteRecord,
                LiteratureItemRecord,
            ):
                self.assertEqual(session.query(model).filter_by(course_code="115-1").count(), 0)
                self.assertEqual(session.query(model).filter_by(course_code="115-1_CP31000").count(), 1)
            self.assertIsNotNone(session.get(KeyPointsRecord, "115-1_CP31000:1"))
            self.assertIsNotNone(session.get(ReviewItemRecord, "flashcard:115-1_CP31000:k1"))
            self.assertIsNotNone(session.get(ExplanationRecord, "115-1_CP31000:qk1"))

            self.assertEqual(session.get(UiPreferenceRecord, "course").value, "115-1_CP31000")  # type: ignore[union-attr]
            self.assertIsNotNone(session.get(UiPreferenceRecord, "place:115-1_CP31000"))
            self.assertIsNone(session.get(UiPreferenceRecord, "place:115-1"))
            self.assertIsNotNone(session.get(UiPreferenceRecord, "examNotice:115-1_CP31000"))
            self.assertIsNotNone(session.get(UiPreferenceRecord, "audio:115-1_CP31000:1"))
            self.assertEqual(session.get(UiPreferenceRecord, "palette").value, "ink")  # type: ignore[union-attr]

            self.assertIn('code = "115-1_CP31000"', (study_dir / "course.toml").read_text(encoding="utf-8"))
            self.assertFalse((self.cfg.notes_state_dir / "115-1.json").exists())
            new_state = json.loads(
                (self.cfg.notes_state_dir / "115-1_CP31000.json").read_text(encoding="utf-8")
            )
            self.assertEqual(new_state["course_key"], "115-1_CP31000")
            self.assertTrue((self.cfg.notes_state_dir / "115-1_CP31000.pause.json").is_file())
            self.assertFalse((self.cfg.scratch_kind_dir("notes") / "115-1").exists())
            self.assertTrue((self.cfg.scratch_kind_dir("notes") / "115-1_CP31000" / "draft.md").is_file())

            qa1 = (study_dir / "03 Notes" / "QA_Notes" / "cn-1_Note.md").read_text(encoding="utf-8")
            self.assertIn('course: "115-1_CP31000"', qa1)
            self.assertIn('course: "115-1" in body stays untouched', qa1)
            qa2 = (study_dir / "03 Notes" / "QA_Notes" / "cn-2_Legacy.md").read_text(encoding="utf-8")
            self.assertIn("course_code: 115-1_CP31000", qa2)

    def test_rename_midway_failure_rolls_back_db_and_files(self) -> None:
        """Scenario 11g: failure midway through file sync rolls back both DB transaction and touched files."""
        with self.session_factory() as session:
            study_dir = self._seed_full_course(session, "115-1")
            c_repo, q_repo = CourseRepository(session), QueueRepository(session)
            lifecycle = CourseLifecycleService(c_repo, q_repo, CourseIdentityRepository(session), self.cfg)

            with mock.patch(
                "notebooklm_batch_studio.services.course_lifecycle._sync_qa_notes_frontmatter",
                side_effect=OSError("disk write failed"),
            ):
                with self.assertRaises(OSError):
                    lifecycle.rename("115-1", "115-1_CP31000", dry_run=False)

            self.assertIsNotNone(c_repo.get_course("115-1"))
            self.assertIsNone(c_repo.get_course("115-1_CP31000"))
            self.assertEqual(session.query(LectureRecord).filter_by(course_code="115-1").count(), 1)
            self.assertIn('code = "115-1"', (study_dir / "course.toml").read_text(encoding="utf-8"))
            self.assertTrue((self.cfg.notes_state_dir / "115-1.json").is_file())
            self.assertFalse((self.cfg.notes_state_dir / "115-1_CP31000.json").exists())
            self.assertTrue((self.cfg.notes_state_dir / "115-1.pause.json").is_file())
            self.assertTrue((self.cfg.scratch_kind_dir("notes") / "115-1" / "draft.md").is_file())


if __name__ == "__main__":
    unittest.main()

"""Dummy-mode end-to-end chaos tests & resolved UI/workflow regression suite (TASK-017, TASK-019)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.learning_repository import LearningRepository
from notebooklm_batch_studio.adapters.db.models import (
    KeyPointsRecord,
    TutorMessageRecord,
    UiPreferenceRecord,
)
from notebooklm_batch_studio.adapters.db.preferences_repository import PreferencesRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.review_repository import ReviewRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, JobStatus
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.services.learning_service import LearningService
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.preferences_service import PreferencesService
from notebooklm_batch_studio.services.study_plan_service import StudyPlanDeps, StudyPlanService
from notebooklm_batch_studio.services.study_service import StudyTrackerService
from tests.dummy_client import DummyStudioClient

STATIC_DIR = (
    Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
)
DESIGN_DIR = Path(__file__).resolve().parents[1] / "docs" / "design"


class DummySimulationFixture(unittest.IsolatedAsyncioTestCase):
    """Full in-memory DB + temp DATA_DIR + FastAPI TestClient wired to DummyStudioClient."""

    def setUp(self) -> None:
        """Create isolated config, database session, services, and HTTP client."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.course_dir = self.tmp / "BIO101 細胞生物學"
        self.course_dir.mkdir()
        (self.course_dir / "Ch01-Membranes.pdf").write_bytes(b"%PDF-1.4\n%membrane\n")
        (self.course_dir / "Ch02-Energy.pdf").write_bytes(b"%PDF-1.4\n%energy\n")

        self.config = AppConfig(
            data_dir=self.tmp / "data",
            notebooklm_home=self.tmp / "cfg",
            log_to_file=False,
            http_allowed_hosts=("testserver",),
        )
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session = session_scope(engine).__enter__()
        self.course_repo = CourseRepository(self.session)
        self.queue_repo = QueueRepository(self.session)
        self.study_repo = StudyRepository(self.session)
        self.review_repo = ReviewRepository(self.session)
        self.learning_repo = LearningRepository(self.session)
        self.client = DummyStudioClient()
        self.service = BatchStudioService(self.course_repo, self.queue_repo, self.client, self.config)
        self.study_service = StudyTrackerService(self.study_repo, config=self.config)
        self.plan_service = StudyPlanService(
            StudyPlanDeps(self.course_repo, self.queue_repo, self.study_repo, self.review_repo, self.client)
        )
        app = create_app(
            config=self.config,
            service=self.service,
            study_service=self.study_service,
            study_plan=self.plan_service,
        )
        app.state.learning = LearningService(self.course_repo, self.learning_repo, self.client)
        app.state.preferences = PreferencesService(PreferencesRepository(self.session))
        self.http = TestClient(app)

    def tearDown(self) -> None:
        """Close DB session and remove temporary directories."""
        self.session.close()
        self.tmpdir.cleanup()


class AllArtifactTypesE2ETest(DummySimulationFixture):
    """Verify every supported artifact type generates, converts, and renders cleanly offline."""

    async def test_all_12_artifact_types_end_to_end(self) -> None:
        """Execute all chapter and course-wide artifact types with DummyStudioClient."""
        self.service.add_course_folders([str(self.course_dir)], paused=True)
        types = [
            (1, ArtifactType.AUDIO),
            (1, ArtifactType.STUDY_GUIDE),
            (1, ArtifactType.REPORTS_BRIEFING),
            (1, ArtifactType.REPORTS_CONCEPT),
            (1, ArtifactType.INFOGRAPHIC),
            (1, ArtifactType.SLIDE_DECK),
            (1, ArtifactType.DATA_TABLE),
            (1, ArtifactType.VIDEO),
            (1, ArtifactType.QUIZ_1),
            (1, ArtifactType.FLASHCARDS),
            (1, ArtifactType.MIND_MAP),
            (None, ArtifactType.COURSE_AUDIO),
            (None, ArtifactType.COURSE_MOCK_EXAM),
            (None, ArtifactType.COURSE_MIND_MAP),
        ]
        jobs = [
            ArtifactJob(id=f"sim-{idx}", course_code="BIO101", lecture_no=lec, artifact_type=art)
            for idx, (lec, art) in enumerate(types, start=1)
        ]
        self.queue_repo.enqueue_jobs(jobs)
        for job in jobs:
            out_path = await self.service.execute_job(job)
            self.assertTrue(Path(out_path).exists(), f"Missing output for {job.artifact_type}")
            self.queue_repo.complete_job(job.id, output_file=out_path)

        artifacts = self.http.get("/api/courses/BIO101/artifacts").json()
        self.assertGreater(len(artifacts), 10)
        quiz_res = self.http.get("/api/courses/BIO101/lectures/1/quiz/quiz_1?with_answers=true")
        self.assertEqual(quiz_res.status_code, 200)
        self.assertGreaterEqual(len(quiz_res.json()["quiz"]["questions"]), 30)
        fc_res = self.http.get("/api/courses/BIO101/study/flashcards?lecture_no=1")
        self.assertEqual(fc_res.status_code, 200)
        self.assertGreaterEqual(len(fc_res.json()["cards"]), 2)
        view_res = self.http.get("/api/artifacts/BIO101/view/01_Membranes/mindmap.opml")
        self.assertEqual(view_res.status_code, 200)
        self.assertIn("細胞生物學總覽", view_res.text)


class NaiveChaosUserJourneyTest(DummySimulationFixture):
    """Simulate a naive/chaos user poking empty states, bad inputs, quota/delete edges, and study loops."""

    def test_chaos_empty_states_and_invalid_inputs(self) -> None:
        """Endpoints degrade gracefully when empty or handed nonsensical user input."""
        self.assertEqual(self.http.get("/api/courses").json(), [])
        self.assertEqual(self.http.get("/api/status").status_code, 200)
        self.assertEqual(self.http.get("/api/courses/NONE").status_code, 404)
        self.assertEqual(self.http.get("/api/courses/NONE/study/plan").status_code, 404)
        self.assertEqual(self.http.delete("/api/courses/NONE").status_code, 404)
        self.assertIn(
            self.http.post("/api/courses", json={"paths": ["/no/such/folder"]}).status_code, (400, 422)
        )
        self.assertEqual(
            self.http.put("/api/preferences", json={"values": {"bad key!": "1"}}).status_code, 400
        )

    async def test_chaos_lifecycle_quiz_review_delete_and_reregister(self) -> None:
        """Rapid start/pause/quota/study/delete/re-add flows leave zero orphans or crashes."""
        self.service.add_course_folders([str(self.course_dir)], paused=True)
        await self.service.setup_notebook_and_sources("BIO101")
        # Toggle selection so half are skipped, check 100% calculation on remaining done jobs (ISSUE-036)
        self.service.course_settings.set_artifact_selection("BIO101", ["audio"], [])
        active_audio = [
            j for j in self.queue_repo.list_jobs("BIO101") if j.artifact_type == ArtifactType.AUDIO
        ]
        for idx, job in enumerate(active_audio, start=1):
            self.queue_repo.complete_job(job.id, output_file=str(self.tmp / f"a{idx}.m4a"))
        summary = self.http.get("/api/courses").json()[0]
        self.assertEqual(summary["progress_percent"], 100.0)

        # Quota block & manual wake recovery (ISSUE-035)
        self.queue_repo.enqueue_jobs(
            [ArtifactJob(id="q-wait", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.VIDEO)]
        )
        self.queue_repo.block_job_quota("q-wait", ArtifactType.VIDEO, cooldown_seconds=7200)
        self.assertEqual(self.http.post("/api/queue/resume").status_code, 200)
        self.assertEqual(self.queue_repo.get_job("q-wait").status, JobStatus.PENDING)  # type: ignore[union-attr]

        # Exercise study plan, quiz mistake, review, and tutor
        self.assertEqual(
            self.http.post(
                "/api/courses/BIO101/study/progress", json={"lecture_no": 1, "step": "audio", "done": True}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.http.post(
                "/api/courses/BIO101/study/quiz-attempts",
                json={
                    "lecture_no": 1,
                    "quiz_variant": "quiz_1",
                    "score": 0,
                    "total_questions": 2,
                    "mistakes": [
                        {
                            "question_text": "Q1?",
                            "choices": ["A", "B"],
                            "correct_index": 0,
                            "selected_index": 1,
                            "explanation": "Why",
                        }
                    ],
                },
            ).status_code,
            200,
        )
        self.assertEqual(
            self.http.post(
                "/api/courses/BIO101/study/tutor", json={"lecture_no": 1, "message": "為什麼？"}
            ).status_code,
            200,
        )
        self.http.put(
            "/api/preferences", json={"values": {"course": "BIO101", "place:BIO101": "1", "palette": "clay"}}
        )

        # Extreme/past exam date accepted safely
        self.assertEqual(
            self.http.put(
                "/api/courses/BIO101/options", json={"options": {"exam_date": "2020-01-01"}}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.http.put("/api/courses/BIO101/options", json={"options": {"exam_date": "bad"}}).status_code,
            422,
        )

        # Delete leaves zero DB orphans for BIO101 while keeping global prefs (ISSUE-034)
        self.assertEqual(self.http.delete("/api/courses/BIO101").status_code, 200)
        self.assertIsNone(self.session.get(UiPreferenceRecord, "course"))
        self.assertIsNone(self.session.get(UiPreferenceRecord, "place:BIO101"))
        self.assertIsNotNone(self.session.get(UiPreferenceRecord, "palette"))
        self.assertEqual(self.session.query(TutorMessageRecord).filter_by(course_code="BIO101").count(), 0)
        self.assertEqual(self.session.query(KeyPointsRecord).filter_by(course_code="BIO101").count(), 0)
        self.assertEqual(self.http.get("/api/courses").json(), [])

        # User can cleanly re-add the deleted folder
        self.service.add_course_folders([str(self.course_dir)], paused=True)
        self.assertEqual(len(self.http.get("/api/courses").json()), 1)


class UiAndStaticRegressionTest(unittest.TestCase):
    """Automated regression verification for UI/CSS/JS known issues without headless browser (TASK-019)."""

    def test_ui_and_static_issue_regressions(self) -> None:
        """Verify structural invariants for ISSUE-018, 022, 026, 029, 031, 032, 034, 036."""
        app_js = (STATIC_DIR / "studio-app.js").read_text(encoding="utf-8")
        batch_js = (STATIC_DIR / "studio-batch.js").read_text(encoding="utf-8")
        core_js = (STATIC_DIR / "studio-core.js").read_text(encoding="utf-8")
        shell_js = (STATIC_DIR / "studio-shell.js").read_text(encoding="utf-8")
        start_js = (STATIC_DIR / "studio-start.js").read_text(encoding="utf-8")
        studio_css = (STATIC_DIR / "studio.css").read_text(encoding="utf-8")
        mockups_html = (DESIGN_DIR / "mockups_gallery.html").read_text(encoding="utf-8")

        # ISSUE-018: dynamic quiz variant support including quiz_1/2/3 & course_mock_exam
        for q_key in ("quiz_1", "quiz_2", "quiz_3", "course_mock_exam"):
            self.assertIn(q_key, app_js)
        # ISSUE-022: submitting quiz keeps current lecture/tab via keepView = true
        self.assertIn("loadStudyCourseData(code, true)", app_js)
        # ISSUE-026: simulated mobile viewport triggers container attribute alongside media query
        self.assertIn('[data-device="iphone"]', mockups_html)
        # ISSUE-029 & ISSUE-031 & ISSUE-032: CSS layout stability
        # (overflow-x: clip, fixed sidebar, scrollbar gutter, no overflow-x hidden on html/body)
        self.assertNotIn("overflow-x: hidden", studio_css.split("/* ====")[0])
        self.assertIn("position: fixed; top: 0; bottom: 0;", studio_css)
        self.assertIn("scrollbar-gutter: stable", studio_css)
        self.assertIn("scrollTo({ top: 0", shell_js)
        # ISSUE-034 & ISSUE-036 & ISSUE-038 & TASK-018: cleanup + progress + failed rerun + StudioBus
        queue_js = (STATIC_DIR / "studio-queue.js").read_text(encoding="utf-8")
        self.assertIn("clearCoursePreferences(code)", batch_js)
        self.assertIn("j.status !== 'skipped'", batch_js)
        self.assertIn("retryJob(", batch_js)
        self.assertIn("retryFailedJobs(", batch_js)
        self.assertIn("/api/courses/${code}/jobs/retry-failed", queue_js)
        self.assertIn("fetchCourses()", start_js)
        self.assertIn("window.StudioBus", core_js)
        self.assertIn("window.StudioStore", core_js)


if __name__ == "__main__":
    unittest.main()

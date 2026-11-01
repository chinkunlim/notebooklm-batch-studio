"""Tests: study plan (next step, progress, exam countdown), spaced review, explanations, chapter tags."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.review_repository import ReviewRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    Lecture,
    QuizAttempt,
)
from notebooklm_batch_studio.domain.study_plan import next_schedule
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.converters.quiz_converter import parse_notebooklm_quiz
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.study_plan_service import StudyPlanService, card_key, days_until
from notebooklm_batch_studio.services.study_service import StudyTrackerService

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


class ScheduleTest(unittest.TestCase):
    """Spaced-review schedule and exam countdown."""

    def test_intervals_and_forgetting(self) -> None:
        """Remembered moves 1 -> 3 -> 7 days; forgotten returns in 10 minutes at stage 0."""
        stage, due = next_schedule(0, True, NOW)
        self.assertEqual((stage, due), (1, NOW + timedelta(days=1)))
        stage, due = next_schedule(2, True, NOW)
        self.assertEqual((stage, due), (3, NOW + timedelta(days=7)))
        stage, due = next_schedule(5, True, NOW)
        self.assertEqual(due, NOW + timedelta(days=30))
        self.assertEqual(next_schedule(3, False, NOW), (0, NOW + timedelta(minutes=10)))

    def test_days_until(self) -> None:
        """Valid dates count days; missing or malformed dates give None."""
        self.assertEqual(days_until("2026-11-11", NOW.date()), 10)
        self.assertIsNone(days_until("", NOW.date()))
        self.assertIsNone(days_until("soon", NOW.date()))

    def test_chapter_tag_becomes_source(self) -> None:
        """ "【Ch03】" at the start of a course exam question becomes its source and leaves the stem."""
        raw = {
            "questions": [
                {"question": "【Ch03】 何者正確？", "answerOptions": [{"text": "a", "isCorrect": True}]}
            ]
        }
        q = parse_notebooklm_quiz(raw, "C", 0).questions[0]
        self.assertEqual((q.question, q.source), ("何者正確？", "Ch03"))


class PlanFixture(unittest.TestCase):
    """In-memory DB with a two-lecture course, some finished outputs and a study-plan service."""

    def setUp(self) -> None:
        """Create database, course, jobs and services."""
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.config = AppConfig(data_dir=tmp, log_to_file=False, http_allowed_hosts=("testserver",))
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session = session_scope(engine).__enter__()
        self.course_repo = CourseRepository(self.session)
        self.queue_repo = QueueRepository(self.session)
        self.study_repo = StudyRepository(self.session)
        self.course_repo.save_course(
            Course(
                code="C1",
                name="課",
                source_dir=str(tmp),
                notebook_id="nb",
                exam_date="2026-11-11",
                lectures=[
                    Lecture(no=1, topic="a", filename="01.pdf", sha256="a", source_id="s1"),
                    Lecture(no=2, topic="b", filename="02.pdf", sha256="b", source_id="s2"),
                ],
            )
        )
        jobs = [
            ArtifactJob(id=f"{no}-{t}", course_code="C1", lecture_no=no, artifact_type=ArtifactType(t))
            for no in (1, 2)
            for t in ("audio", "study_guide", "quiz_1", "flashcards")
        ]
        self.queue_repo.enqueue_jobs(jobs)
        for j in jobs:
            self.queue_repo.complete_job(j.id, "/x")
        self.client = mock.MagicMock()
        self.client.ask = mock.AsyncMock(return_value="因為……")
        self.plan = StudyPlanService(
            self.course_repo, self.queue_repo, self.study_repo, ReviewRepository(self.session), self.client
        )

    def tearDown(self) -> None:
        """Close the session and remove temporary files."""
        self.session.close()
        self.tmpdir.cleanup()


class PlanTest(PlanFixture):
    """Next step, progress, reviews, explanations."""

    def test_next_step_follows_order_and_progress(self) -> None:
        """Audio first; marking steps and a quiz attempt moves the next step on and raises percent."""
        plan = self.plan.get_plan("C1", now=NOW)
        self.assertEqual(plan["days_left"], 10)
        self.assertEqual(plan["next"]["step"], "audio")
        steps = {s["step"]: s for s in plan["lectures"][0]["steps"]}
        self.assertFalse(steps["quiz_2"]["available"])

        self.plan.mark_step("C1", 1, "audio")
        self.plan.mark_step("C1", 1, "guide")
        self.study_repo.record_attempt(
            QuizAttempt(
                id="a1",
                course_code="C1",
                lecture_no=1,
                quiz_variant="quiz_1_v2",
                score=20,
                total_questions=30,
            )
        )
        plan = self.plan.get_plan("C1", now=NOW)
        self.assertEqual(plan["next"]["step"], "flashcards")
        self.assertEqual(plan["lectures"][0]["percent"], 75)
        with self.assertRaises(ValueError):
            self.plan.mark_step("C1", 1, "quiz_1")

    def test_review_schedule_and_due(self) -> None:
        """A reviewed card is due again after its interval; forgotten cards come back soon."""
        key = card_key("什麼是假設？")
        self.plan.record_review("C1", "flashcard", key, True, 1, "什麼是假設？", "可檢驗的預測", now=NOW)
        self.assertEqual(self.plan.due_reviews("C1", now=NOW), [])
        due = self.plan.due_reviews("C1", now=NOW + timedelta(days=1, minutes=1))
        self.assertEqual(due[0]["front"], "什麼是假設？")
        self.plan.record_review("C1", "flashcard", key, False, now=NOW + timedelta(days=1))
        self.assertEqual(self.plan.due_reviews("C1", now=NOW + timedelta(days=1, minutes=11))[0]["stage"], 0)
        self.assertTrue(self.plan.get_plan("C1", now=NOW)["lectures"][0]["steps"][-1]["done"])
        with self.assertRaises(ValueError):
            self.plan.record_review("C1", "nope", key, True)

    def test_explain_uses_lecture_sources(self) -> None:
        """The explanation asks Gemini Notebook with only that lecture's source and the correct letter."""
        out = asyncio.run(self.plan.explain("C1", 2, "哪個對？", ["甲", "乙"], 1))
        self.assertEqual(out["answer"], "因為……")
        args = self.client.ask.await_args.args
        self.assertEqual((args[0], args[2]), ("nb", ["s2"]))
        self.assertIn("正確答案是 B", args[1])
        with self.assertRaises(ValueError):
            asyncio.run(self.plan.explain("C1", 2, "q", ["a"], 3))
        # Markdown from Gemini Notebook is rendered with raw HTML escaped.
        self.client.ask = mock.AsyncMock(return_value="**重點** <script>x</script>")
        html = asyncio.run(self.plan.explain("C1", 2, "q", ["a", "b"], 0))["html"]
        self.assertIn("<strong>重點</strong>", html)
        self.assertNotIn("<script>", html)

    def test_explanations_are_saved_and_reused(self) -> None:
        """The second request for the same question uses the saved answer; force asks again."""
        first = asyncio.run(self.plan.explain("C1", 1, "什麼是假設？", ["a", "b"], 0))
        second = asyncio.run(self.plan.explain("C1", 1, "什麼是假設？", ["a", "b"], 0))
        self.assertFalse(first["from_cache"])
        self.assertTrue(second["from_cache"])
        self.assertEqual(self.client.ask.await_count, 1)
        asyncio.run(self.plan.explain("C1", 1, "什麼是假設？", ["a", "b"], 0, force=True))
        self.assertEqual(self.client.ask.await_count, 2)
        saved = self.plan.list_explanations("C1", 1)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["question"], "什麼是假設？")
        self.assertIn("<p>", saved[0]["html"])

    def test_exam_date_setting_and_delete_clears_study_data(self) -> None:
        """Exam date is editable and validated; deleting the course removes progress and reviews."""
        service = BatchStudioService(self.course_repo, self.queue_repo, mock.MagicMock(), self.config)
        out = service.course_settings.set_options("C1", {"exam_date": "2027-01-15"})
        self.assertEqual(out["options"]["exam_date"], "2027-01-15")
        with self.assertRaises(ValueError):
            service.course_settings.set_options("C1", {"exam_date": "next week"})
        self.plan.mark_step("C1", 1, "audio")
        self.plan.record_review("C1", "flashcard", "k", True, 1, "f", "b", now=NOW)
        asyncio.run(self.plan.explain("C1", 1, "q?", ["a"], 0))
        service.course_settings.delete_course("C1")
        self.assertEqual(ReviewRepository(self.session).list_steps("C1"), set())
        self.assertEqual(ReviewRepository(self.session).list_explanations("C1"), [])
        self.assertEqual(self.plan.due_reviews("C1", now=NOW + timedelta(days=5)), [])


class EntrypointTest(PlanFixture):
    """HTTP routes and MCP tools for the study plan."""

    def test_http_and_mcp(self) -> None:
        """Plan, progress, reviews and explain routes; MCP writes need confirm."""
        service = BatchStudioService(self.course_repo, self.queue_repo, self.client, self.config)
        study = StudyTrackerService(study_repo=self.study_repo, config=self.config)
        http = TestClient(
            create_app(config=self.config, service=service, study_service=study, study_plan=self.plan)
        )
        self.assertEqual(http.get("/api/courses/C1/study/plan").json()["next"]["step"], "audio")
        self.assertEqual(
            http.post("/api/courses/C1/study/progress", json={"lecture_no": 1, "step": "audio"}).status_code,
            200,
        )
        self.assertEqual(
            http.post("/api/courses/C1/study/progress", json={"step": "quiz_1"}).status_code, 422
        )
        body = {
            "kind": "flashcard",
            "key": "k1",
            "remembered": True,
            "lecture_no": 1,
            "front": "f",
            "back": "b",
        }
        self.assertEqual(http.post("/api/courses/C1/study/reviews", json=body).json()["stage"], 1)
        self.assertEqual(http.get("/api/courses/C1/study/reviews/due").json(), [])
        explain = {"question": "q", "choices": ["a", "b"], "answer_index": 0, "lecture_no": 1}
        self.assertEqual(http.post("/api/courses/C1/study/explain", json=explain).json()["answer"], "因為……")
        self.assertEqual(http.get("/api/courses/NOPE/study/plan").status_code, 404)

        mcp = build_mcp_server(service=service, study_service=study, config=self.config, study_plan=self.plan)
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        self.assertIn("next", json.loads(tools["get_study_plan"].fn("C1")))
        self.assertFalse(json.loads(tools["mark_study_step"].fn("C1", "guide", 1))["confirmed"])
        self.assertFalse(
            json.loads(asyncio.run(tools["explain_question"].fn("C1", "q", ["a"], 0)))["confirmed"]
        )


if __name__ == "__main__":
    unittest.main()


class SessionLeakTest(unittest.TestCase):
    """Request-scoped sessions: many requests never exhaust the connection pool (ISSUE-023)."""

    def test_many_requests_release_connections(self) -> None:
        """60 requests through the real app (real sessions, file DB) all succeed and none stay open."""
        from notebooklm_batch_studio.adapters.db.base import Base as DbBase
        from notebooklm_batch_studio.entrypoints import api as api_module

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            db_url = f"sqlite:///{tmp / 'app.db'}"
            engine = create_db_engine(db_url)
            DbBase.metadata.create_all(engine)
            cfg = AppConfig(
                data_dir=tmp, database_url=db_url, log_to_file=False, http_allowed_hosts=("testserver",)
            )
            with mock.patch.object(api_module, "create_db_engine", return_value=engine):
                http = TestClient(create_app(config=cfg))
            for _ in range(60):
                self.assertEqual(http.get("/api/courses").status_code, 200)
            self.assertEqual(engine.pool.checkedout(), 0)

"""Learning aids: key points, lecture PDF reader, forgetting curve, streaks and the tutor (SPEC-008)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.learning_repository import LearningRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.memory_model import (
    activity_heatmap,
    card_stability,
    lecture_memory,
    quiz_stability,
    retention,
    study_streak,
)
from notebooklm_batch_studio.domain.models import Course, Lecture
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.learning_service import LearningService, parse_key_points
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


class KeyPointParsingTest(unittest.TestCase):
    """parse_key_points reads Gemini Notebook's answer robustly."""

    def test_fenced_json_with_citations_is_cleaned(self) -> None:
        """Citation markers go, importance is clamped, bad items and duplicates are dropped."""
        answer = (
            "以下是重點：\n```json\n["
            '{"quote": "Science is a systematic way of knowing [1]", "page": 2, '
            '"importance": 5, "note": "定義"},'
            '{"quote": "Science is a systematic way of knowing", "page": 2, "importance": 3},'
            '{"quote": "ok", "page": 1},'
            '{"quote": "Replication builds trust [2, 3]", "page": "x", "importance": "high"}'
            "]\n```"
        )
        points = parse_key_points(answer)
        self.assertEqual(
            [p["quote"] for p in points],
            ["Science is a systematic way of knowing", "Replication builds trust"],
        )
        self.assertEqual(points[0]["importance"], 3)
        self.assertEqual((points[1]["page"], points[1]["importance"]), (None, 2))

    def test_bare_array_and_garbage(self) -> None:
        """A bare array works; text without JSON raises ValueError."""
        self.assertEqual(len(parse_key_points('前言 [{"quote": "Validity matters", "page": 4}] 結尾')), 1)
        with self.assertRaises(ValueError):
            parse_key_points("沒有 JSON")


class MemoryModelTest(unittest.TestCase):
    """Forgetting curve, stability, streaks and heatmap."""

    def test_retention_and_stability(self) -> None:
        """Retention decays with time; good quiz scores and higher card stages make memory last longer."""
        self.assertAlmostEqual(retention(0, 3), 1.0)
        self.assertLess(retention(6, 3), retention(3, 3))
        good = [(NOW - timedelta(days=d), 0.9) for d in (7, 3)]
        bad = [(NOW - timedelta(days=d), 0.4) for d in (7, 3)]
        self.assertGreater(quiz_stability(good), quiz_stability(bad))
        self.assertAlmostEqual(retention(7, card_stability(3)), retention(1, card_stability(1)), places=6)

    def test_lecture_memory_levels(self) -> None:
        """A fresh good quiz is strong; an old weak one is weak; nothing practised is None."""
        fresh = lecture_memory([(NOW - timedelta(hours=2), 0.9)], [], NOW)
        old = lecture_memory([(NOW - timedelta(days=10), 0.5)], [], NOW)
        self.assertEqual(fresh["level"], "strong")  # type: ignore[index]
        self.assertEqual(old["level"], "weak")  # type: ignore[index]
        self.assertIsNone(lecture_memory([], [], NOW))

    def test_streak_and_heatmap(self) -> None:
        """The streak counts back from today (or yesterday); the heatmap covers 28 days."""
        today = date(2026, 11, 1)
        days = {today, today - timedelta(days=1), today - timedelta(days=2), today - timedelta(days=4)}
        self.assertEqual(study_streak(days, today), 3)
        self.assertEqual(study_streak(days - {today}, today), 2)
        self.assertEqual(study_streak(set(), today), 0)
        heat = activity_heatmap([NOW, NOW], today)
        self.assertEqual(len(heat), 28)
        self.assertEqual(heat[-1], {"date": "2026-11-01", "count": 2})


class LearningServiceTest(unittest.TestCase):
    """Reader, key points, memory and tutor through the service, HTTP and MCP."""

    def setUp(self) -> None:
        """Create a course folder with one PDF, the database and a fake Gemini Notebook client."""
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.folder = tmp / "BIO101 細胞"
        self.folder.mkdir()
        (self.folder / "01_ch_cells.pdf").write_bytes(b"%PDF-1.4 test")
        self.config = AppConfig(
            data_dir=tmp / "data",
            notebooklm_home=tmp / "cfg",
            log_to_file=False,
            http_allowed_hosts=("testserver",),
        )
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session = session_scope(engine).__enter__()
        course_repo = CourseRepository(self.session)
        course_repo.save_course(
            Course(
                code="BIO101",
                name="細胞",
                source_dir=str(self.folder),
                notebook_id="nb1",
                lectures=[
                    Lecture(no=1, topic="cells", filename="01_ch_cells.pdf", sha256="a", source_id="s1"),
                    Lecture(no=2, topic="evil", filename="../../etc/passwd", sha256="b", source_id="s2"),
                ],
            )
        )
        self.client = mock.MagicMock()
        self.client.ask = mock.AsyncMock(return_value='[{"quote": "Cells are the unit of life", "page": 1}]')
        self.client.ask_in_conversation = mock.AsyncMock(
            side_effect=[("第四個目標是什麼 [1-3]？", "conv-1"), ("對！下一步？", "conv-1")]
        )
        self.repo = LearningRepository(self.session)
        self.learning = LearningService(course_repo, self.repo, self.client)
        service = BatchStudioService(course_repo, QueueRepository(self.session), self.client, self.config)
        app = create_app(config=self.config, service=service, study_service=mock.MagicMock())
        app.state.learning = self.learning
        self.http = TestClient(app)

    def tearDown(self) -> None:
        """Close the session and remove temporary files."""
        self.session.close()
        self.tmpdir.cleanup()

    def test_pdf_is_served_read_only_and_never_outside_the_folder(self) -> None:
        """The lecture PDF is shown inline; a file name escaping the folder is refused."""
        res = self.http.get("/api/courses/BIO101/lectures/1/source.pdf")
        self.assertEqual((res.status_code, res.headers["content-type"]), (200, "application/pdf"))
        self.assertIn("inline", res.headers["content-disposition"])
        self.assertEqual(self.http.get("/api/courses/BIO101/lectures/2/source.pdf").status_code, 403)
        self.assertEqual(self.http.get("/api/courses/BIO101/lectures/9/source.pdf").status_code, 404)
        self.assertEqual((self.folder / "01_ch_cells.pdf").read_bytes(), b"%PDF-1.4 test")

    def test_key_points_are_asked_once_then_reused(self) -> None:
        """The first request asks Gemini Notebook with only that lecture; the second reuses the saved copy."""
        self.assertEqual(self.http.get("/api/courses/BIO101/lectures/1/key-points").json()["points"], [])
        first = self.http.post("/api/courses/BIO101/lectures/1/key-points", json={}).json()
        second = self.http.post("/api/courses/BIO101/lectures/1/key-points", json={}).json()
        self.assertEqual(first["points"][0]["quote"], "Cells are the unit of life")
        self.assertEqual((first["from_cache"], second["from_cache"]), (False, True))
        self.assertEqual(self.client.ask.await_count, 1)
        self.assertEqual(self.client.ask.await_args.args[2], ["s1"])

    def test_tutor_continues_one_conversation(self) -> None:
        """The second message continues the first conversation; both sides are saved."""
        self.http.post("/api/courses/BIO101/study/tutor", json={"lecture_no": 1, "message": "什麼是細胞？"})
        self.http.post("/api/courses/BIO101/study/tutor", json={"lecture_no": 1, "message": "生命的單位"})
        self.assertIsNone(self.client.ask_in_conversation.await_args_list[0].args[3])
        self.assertEqual(self.client.ask_in_conversation.await_args_list[1].args[3], "conv-1")
        history = self.http.get("/api/courses/BIO101/study/tutor?lecture_no=1").json()
        self.assertEqual([m["role"] for m in history], ["student", "tutor", "student", "tutor"])
        self.assertEqual(history[1]["text"], "第四個目標是什麼？")  # citation markers removed
        self.assertTrue(self.http.delete("/api/courses/BIO101/study/tutor?lecture_no=1").json()["cleared"])
        self.assertEqual(self.http.get("/api/courses/BIO101/study/tutor?lecture_no=1").json(), [])

    def test_memory_endpoint(self) -> None:
        """Memory lists every lecture; nothing practised yet means no percentage and no streak."""
        data = self.http.get("/api/courses/BIO101/study/memory").json()
        self.assertEqual([lec["no"] for lec in data["lectures"]], [1, 2])
        self.assertIsNone(data["lectures"][0]["percent"])
        self.assertEqual((data["streak"], len(data["heatmap"])), (0, 28))

    def test_confidence_is_saved_with_mistakes_and_attempt(self) -> None:
        """A 'sure' wrong answer keeps its confidence; unknown values are dropped; the summary is stored."""
        from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
        from notebooklm_batch_studio.services.study_service import StudyTrackerService

        study = StudyTrackerService(study_repo=StudyRepository(self.session), config=self.config)
        mistake = {
            "question_text": "Q",
            "choices": ["a", "b"],
            "correct_index": 0,
            "selected_index": 1,
            "explanation": "",
        }
        study.record_quiz_attempt(
            "BIO101",
            1,
            "quiz_1",
            8,
            10,
            [{**mistake, "confidence": "sure"}, {**mistake, "question_text": "Q2", "confidence": "maybe"}],
            confidence_summary={"sure_wrong": 1, "guess_right": 2},
        )
        saved = sorted(study.get_weaknesses("BIO101"), key=lambda m: m.question_text)
        self.assertEqual([m.confidence for m in saved], ["sure", None])
        memory = self.learning.memory("BIO101")
        self.assertIsNotNone(memory["lectures"][0]["percent"])
        self.assertTrue(memory["studied_today"])

    def test_mcp_tools_need_confirm(self) -> None:
        """Calling Gemini Notebook from MCP needs confirm=True; reading does not."""
        mcp = build_mcp_server(
            service=mock.MagicMock(),
            study_service=mock.MagicMock(),
            config=self.config,
            learning=self.learning,
        )
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        self.assertEqual(json.loads(tools["get_key_points"].fn("BIO101", 1))["points"], [])
        self.assertIn("streak", json.loads(tools["get_memory_strength"].fn("BIO101")))
        self.assertIn("generate_key_points", tools)
        self.assertIn("ask_tutor", tools)


if __name__ == "__main__":
    unittest.main()

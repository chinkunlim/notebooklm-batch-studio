"""SPEC-006 tests: course-wide instructions, per-output settings, course basics, custom video style."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from notebooklm import VideoStyle

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.notebooklm.generation import generation_kwargs
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    GenerationOptions,
    Lecture,
    effective_options,
)
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.course_settings import apply_job_settings, fields_for_type
from notebooklm_batch_studio.services.orchestrator import BatchStudioService


class MergeTest(unittest.TestCase):
    """How course options, output overrides and instructions combine."""

    def test_effective_options_and_extra_instructions(self) -> None:
        """Overrides win field by field; extra instructions from both levels are kept."""
        course = GenerationOptions(extra_instructions="考申論", quiz_questions=30)
        merged = effective_options(course, {"quiz_questions": 20, "extra_instructions": "多出圖表題"})
        self.assertEqual(merged.quiz_questions, 20)
        self.assertEqual(merged.extra_instructions, "考申論\n多出圖表題")

    def test_apply_job_settings_appends_instructions_and_forces_difficulty(self) -> None:
        """The run-time job prompt gets the instructions; a forced difficulty reaches the course options."""
        course = Course(
            code="C",
            name="n",
            source_dir="/x",
            generation_options=GenerationOptions(extra_instructions="考申論"),
        )
        job = ArtifactJob(
            id="j",
            course_code="C",
            lecture_no=1,
            artifact_type=ArtifactType.QUIZ_1,
            custom_prompt="出 30 題",
            style_options=json.dumps({"quiz_difficulty": "hard"}),
        )
        run_job, run_course = apply_job_settings(job, course)
        self.assertEqual(run_job.custom_prompt, "出 30 題\n\n補充要求：考申論")
        self.assertEqual(run_course.generation_options.quiz_difficulty, "hard")

    def test_question_counts_drive_prompt_and_quantity(self) -> None:
        """quiz_questions sets the prompt count and quiz size; the mock exam uses the course count."""
        from notebooklm import QuizQuantity

        from notebooklm_batch_studio.adapters.notebooklm.generation import quiz_quantity_for

        self.assertEqual(
            [quiz_quantity_for(n) for n in (10, 20, 30)],
            [QuizQuantity.FEWER, QuizQuantity.STANDARD, QuizQuantity.MORE],
        )
        course = Course(
            code="C",
            name="n",
            source_dir="/x",
            mock_exam_questions=70,
            generation_options=GenerationOptions(quiz_questions=20),
        )
        quiz = ArtifactJob(
            id="a",
            course_code="C",
            lecture_no=1,
            artifact_type=ArtifactType.QUIZ_1,
            custom_prompt="請生成 30 題【測驗】",
        )
        mock_job = ArtifactJob(
            id="b",
            course_code="C",
            lecture_no=None,
            artifact_type=ArtifactType.COURSE_MOCK_EXAM,
            custom_prompt="請生成 50 題跨章節",
        )
        self.assertIn("生成 20 題", apply_job_settings(quiz, course)[0].custom_prompt or "")
        self.assertIn("生成 70 題", apply_job_settings(mock_job, course)[0].custom_prompt or "")

    def test_custom_video_style_uses_custom_enum(self) -> None:
        """A style description switches to VideoStyle.CUSTOM; short videos drop it."""
        kwargs = generation_kwargs("video", GenerationOptions(video_style_prompt="手繪粉筆風"))
        self.assertEqual(kwargs["video_style"], VideoStyle.CUSTOM)
        self.assertEqual(kwargs["style_prompt"], "手繪粉筆風")
        short = generation_kwargs("video", GenerationOptions(video_format="short", video_style_prompt="x"))
        self.assertNotIn("style_prompt", short)

    def test_fields_per_type(self) -> None:
        """Each output type exposes only its own options plus extra instructions."""
        self.assertEqual(
            fields_for_type("quiz_2"), ["quiz_questions", "quiz_difficulty", "extra_instructions"]
        )
        self.assertIn("infographic_orientation", fields_for_type("course_infographic"))
        self.assertEqual(fields_for_type("study_guide"), ["extra_instructions"])


class ServiceTest(unittest.TestCase):
    """Course basics, per-output settings, and their entry points."""

    def setUp(self) -> None:
        """Create database, course and service."""
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.config = AppConfig(
            data_dir=tmp / "data",
            notebooklm_home=tmp / "cfg",
            log_to_file=False,
            http_allowed_hosts=("testserver",),
        )
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session = session_scope(engine).__enter__()
        self.queue_repo = QueueRepository(self.session)
        course_repo = CourseRepository(self.session)
        course_repo.save_course(
            Course(
                code="BIO101",
                name="細胞生物學",
                source_dir=str(tmp),
                lectures=[Lecture(no=1, topic="a", filename="01_ch_a.pdf", sha256="a")],
            )
        )
        self.service = BatchStudioService(course_repo, self.queue_repo, mock.MagicMock(), self.config)
        self.queue_repo.enqueue_jobs(
            [ArtifactJob(id="q", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1)]
        )

    def tearDown(self) -> None:
        """Close the session and remove temporary files."""
        self.session.close()
        self.tmpdir.cleanup()

    def test_course_language_and_mock_exam_count(self) -> None:
        """Language and mock exam count are editable and validated."""
        settings = self.service.course_settings
        out = settings.set_options("BIO101", {"language": "en", "mock_exam_questions": 60})
        self.assertEqual((out["options"]["language"], out["options"]["mock_exam_questions"]), ("en", 60))
        for bad in ({"language": "fr"}, {"mock_exam_questions": 500}, {"mock_exam_questions": "50"}):
            with self.assertRaises(ValueError):
                settings.set_options("BIO101", bad)

    def test_job_options_validate_store_and_carry_over(self) -> None:
        """Own settings are validated per type, stored, and copied to a regenerated version."""
        settings = self.service.course_settings
        out = settings.set_job_options("q", {"quiz_questions": 15, "quiz_difficulty": ""})
        self.assertEqual(out["overrides"], {"quiz_questions": 15})
        self.assertEqual(out["effective"]["quiz_questions"], 15)
        self.assertEqual(out["defaults"]["quiz_questions"], 30)
        with self.assertRaises(ValueError):
            settings.set_job_options("q", {"audio_format": "brief"})
        new_id = settings.regenerate("BIO101", 1, "quiz_1")["job_id"]
        self.assertEqual(json.loads(self.queue_repo.get_job(new_id).style_options), {"quiz_questions": 15})  # type: ignore[union-attr,arg-type]

    def test_http_and_mcp(self) -> None:
        """GET/PUT /api/jobs/{id}/options and the MCP tool (confirm required)."""
        http = TestClient(
            create_app(config=self.config, service=self.service, study_service=mock.MagicMock())
        )
        data = http.get("/api/jobs/q/options").json()
        self.assertIn("quiz_questions", data["fields"])
        self.assertTrue(data["unsupported"])
        self.assertEqual(
            http.put("/api/jobs/q/options", json={"options": {"slide_format": "x"}}).status_code, 422
        )
        self.assertEqual(http.get("/api/jobs/missing/options").status_code, 404)
        mcp = build_mcp_server(service=self.service, study_service=mock.MagicMock(), config=self.config)
        tool = mcp._tool_manager._tools["set_job_options"].fn  # type: ignore[attr-defined]
        self.assertFalse(json.loads(tool("q", {"quiz_questions": 15}))["confirmed"])


if __name__ == "__main__":
    unittest.main()

"""Unit tests for BatchStudioService, CourseReporter, CourseWatcher, and CLI commands.

Tests end-to-end orchestration, artifact generation callbacks, quarantine of incomplete
quizzes into needs_review/, summary generation, filesystem observation, and CLI entrypoints.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import NeedsReviewError
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    JobStatus,
    Lecture,
    ProfileName,
)
from notebooklm_batch_studio.entrypoints.cli import main
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.reporter import CourseReporter
from notebooklm_batch_studio.services.watcher import _wait_for_file_settled

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class MockNotebookLMClient:
    """Mock client implementing NotebookLMClientProtocol for offline unit tests."""

    def __init__(self) -> None:
        """Initialize mock client."""
        self.notebooks_created: list[str] = []
        self.sources_uploaded: list[tuple[str, str]] = []
        self.renamed_artifacts: list[tuple[str, str, str]] = []
        self.storage_path = Path("/mock/storage_state.json")
        self.source_limit: int | None = 50

    def check_auth(self) -> bool:
        """Mock check auth."""
        return True

    async def create_notebook(self, title: str) -> str:
        """Mock create notebook."""
        nb_id = f"mock-nb-{len(self.notebooks_created) + 1}"
        self.notebooks_created.append(nb_id)
        return nb_id

    async def upload_source(self, notebook_id: str, file_path: str) -> str:
        """Mock upload source."""
        source_id = f"src-{Path(file_path).stem}"
        self.sources_uploaded.append((notebook_id, file_path))
        return source_id

    async def wait_source_ready(self, notebook_id: str, source_id: str, timeout_seconds: int = 180) -> None:
        """Mock wait source ready."""
        pass

    async def generate_quiz(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        difficulty: str | None = None,
        options: Any = None,
    ) -> str:
        """Mock generate quiz."""
        return "task-quiz-1"

    async def download_quiz(self, notebook_id: str, output_path: str, artifact_id: str | None = None) -> None:
        """Mock download quiz writing sample fixture."""
        sample_quiz_file = FIXTURES_DIR / "sample_quiz.json"
        content = sample_quiz_file.read_text(encoding="utf-8")
        Path(output_path).write_text(content, encoding="utf-8")

    async def generate_flashcards(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, options: Any = None
    ) -> str:
        """Mock generate flashcards."""
        return "task-fc-1"

    async def download_flashcards(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download flashcards."""
        sample_fc_file = FIXTURES_DIR / "sample_flashcards.json"
        content = sample_fc_file.read_text(encoding="utf-8")
        Path(output_path).write_text(content, encoding="utf-8")

    async def generate_mind_map(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Mock generate mind map."""
        return "task-mm-1"

    async def download_mind_map(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download mind map."""
        sample_mm_file = FIXTURES_DIR / "sample_mindmap.json"
        content = sample_mm_file.read_text(encoding="utf-8")
        Path(output_path).write_text(content, encoding="utf-8")

    async def generate_audio(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: Any = None,
    ) -> str:
        """Mock generate audio."""
        return "task-audio-1"

    async def download_audio(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download audio."""
        Path(output_path).write_bytes(b"MOCK_AUDIO_DATA")

    async def rename_artifact(self, notebook_id: str, artifact_id: str, title: str) -> None:
        """Mock rename artifact."""
        self.renamed_artifacts.append((notebook_id, artifact_id, title))

    async def rename_mind_map(self, notebook_id: str, note_id: str, title: str) -> None:
        """Mock rename mind map."""
        self.renamed_artifacts.append((notebook_id, note_id, title))

    async def generate_report(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Mock generate report."""
        return "task-report-1"

    async def download_report(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download report."""
        Path(output_path).write_text("# Study Guide\nMock content", encoding="utf-8")

    async def generate_slide_deck(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: Any = None,
    ) -> str:
        """Mock generate slide deck."""
        return "task-slide-1"

    async def download_slide_deck(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None, output_format: str = "pdf"
    ) -> None:
        """Mock download slide deck."""
        Path(output_path).write_text("# Slide Deck\nSlide 1: Intro", encoding="utf-8")

    async def generate_infographic(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: Any = None,
    ) -> str:
        """Mock generate infographic."""
        return "task-info-1"

    async def download_infographic(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download infographic."""
        Path(output_path).write_bytes(b"MOCK_PNG")

    async def generate_data_table(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Mock generate data table."""
        return "task-dt-1"

    async def download_data_table(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download data table."""
        Path(output_path).write_text("| Column A | Column B |\n|---|---|\n| 1 | 2 |", encoding="utf-8")

    async def generate_video(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: Any = None,
    ) -> str:
        """Mock generate video."""
        return "task-vid-1"

    async def download_video(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download video."""
        Path(output_path).write_bytes(b"MOCK_MP4")

    async def get_source_limit(self) -> int | None:
        """Mock per-notebook source limit."""
        return self.source_limit

    async def get_quota_status(self) -> dict[str, object]:
        """Mock quota status."""
        return {"status": "ready", "windows": [], "actions": [], "source_limit": self.source_limit}


class TestCourseReporter(unittest.TestCase):
    """Test suite for CourseReporter generating markdown and HTML summaries."""

    def setUp(self) -> None:
        """Set up test course and reporter."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.out_root = Path(self.tmpdir.name)
        self.reporter = CourseReporter(self.out_root)

        self.course = Course(
            code="BIO101",
            name="General Biology",
            source_dir="/tmp/bio101",
            notebook_id="nb-12345",
            profile=ProfileName.FULL,
            lectures=[
                Lecture(no=1, topic="Cell Structure", filename="01_cells.pdf", sha256="abc1"),
                Lecture(no=2, topic="Membrane Transport", filename="02_transport.pdf", sha256="abc2"),
            ],
        )

    def tearDown(self) -> None:
        """Clean up temporary test directory."""
        self.tmpdir.cleanup()

    def test_generate_summary_files(self) -> None:
        """Verify summary.md and summary.html generation and structure."""
        job_statuses = {
            (1, "audio"): JobStatus.DONE,
            (1, "quiz_1"): JobStatus.DONE,
            (2, "audio"): JobStatus.QUOTA_WAIT,
            (None, "course_mock_exam"): JobStatus.DONE,
        }

        md_path, html_path = self.reporter.generate_summary(self.course, job_statuses)

        self.assertTrue(md_path.exists())
        self.assertTrue(html_path.exists())

        md_content = md_path.read_text(encoding="utf-8")
        self.assertIn("# 課程總覽：[BIO101] General Biology", md_content)
        self.assertIn("第 01 講 | Cell Structure", md_content)
        self.assertIn("https://notebooklm.google.com/notebook/nb-12345", md_content)

        html_content = html_path.read_text(encoding="utf-8")
        self.assertIn("<title>[BIO101] General Biology", html_content)
        self.assertIn("badge done", html_content)
        self.assertIn("badge quota", html_content)


class TestBatchStudioService(unittest.IsolatedAsyncioTestCase):
    """Test suite for BatchStudioService execution pipeline."""

    def setUp(self) -> None:
        """Set up in-memory DB and test environment."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)

        self.engine = create_db_engine("sqlite:///:memory:")
        from notebooklm_batch_studio.adapters.db.models import Base

        Base.metadata.create_all(self.engine)

        self.config = AppConfig(
            data_dir=self.tmp_path / "data",
            notebooklm_home=self.tmp_path / "config",
        )
        self.mock_client = MockNotebookLMClient()

    def tearDown(self) -> None:
        """Clean up temporary test directory."""
        self.tmpdir.cleanup()

    async def test_full_course_registration_and_job_execution(self) -> None:
        """Verify course scanning, uploading, queueing, and artifact job processing."""
        # Create a sample course directory
        course_dir = self.tmp_path / "BIO101"
        course_dir.mkdir(parents=True)
        pdf1 = course_dir / "01_Membranes.pdf"
        pdf1.write_bytes(b"%PDF-1.4 mock pdf content 1")
        pdf2 = course_dir / "02_Enzymes.pdf"
        pdf2.write_bytes(b"%PDF-1.4 mock pdf content 2")

        with session_scope(self.engine) as session:
            c_repo = CourseRepository(session)
            q_repo = QueueRepository(session)
            service = BatchStudioService(c_repo, q_repo, self.mock_client, self.config)

            # 1. Register course folder
            course = service.register_course_folder(course_dir)
            self.assertEqual(course.code, "BIO101")
            self.assertEqual(len(course.lectures), 2)

            # 2. Setup NotebookLM notebook and sources
            updated = await service.setup_notebook_and_sources("BIO101")
            self.assertIsNotNone(updated.notebook_id)
            self.assertEqual(len(self.mock_client.sources_uploaded), 2)

            # 3. Enqueue jobs
            enqueued = service.enqueue_course_artifacts("BIO101")
            self.assertTrue(enqueued > 0)

            # 4. Test Flashcards Execution
            fc_job = ArtifactJob(
                id="job-fc-1",
                course_code="BIO101",
                lecture_no=1,
                artifact_type=ArtifactType.FLASHCARDS,
            )
            fc_out = await service.execute_job(fc_job)
            self.assertTrue(Path(fc_out).exists())
            self.assertTrue(fc_out.endswith("anki.csv"))

            # 5. Test Mind Map Execution
            mm_job = ArtifactJob(
                id="job-mm-1",
                course_code="BIO101",
                lecture_no=1,
                artifact_type=ArtifactType.MIND_MAP,
            )
            mm_out = await service.execute_job(mm_job)
            self.assertTrue(Path(mm_out).exists())
            self.assertTrue(mm_out.endswith("mindmap.opml"))

            # 6. Test Quiz Execution (Quarantine test: mock client returns 10 questions < 30)
            quiz_job = ArtifactJob(
                id="job-quiz-1",
                course_code="BIO101",
                lecture_no=1,
                artifact_type=ArtifactType.QUIZ_1,
            )
            # Mock client returns 10 questions (< 30): quiz is quarantined and NeedsReviewError raised
            with self.assertRaises(NeedsReviewError) as ctx:
                await service.execute_job(quiz_job)
            self.assertTrue(Path(ctx.exception.output_file).exists())
            self.assertIn("needs_review", ctx.exception.output_file)


class TestCourseWatcher(unittest.TestCase):
    """Test suite for CourseWatcher filesystem monitor."""

    def test_file_settled_probe(self) -> None:
        """Verify _wait_for_file_settled detects stable files."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"SAMPLE CONTENT")
            f_path = Path(f.name)

        try:
            self.assertTrue(_wait_for_file_settled(f_path, max_wait=2.0, check_interval=0.1))
        finally:
            f_path.unlink(missing_ok=True)


class TestCliCommands(unittest.TestCase):
    """Test suite for CLI subcommands."""

    def test_cli_greeting(self) -> None:
        """Verify bootstrap greeting argument."""
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--name", "Developer"])
        self.assertEqual(code, 0)
        self.assertIn("Hello, Developer!", out.getvalue())

    def test_cli_status(self) -> None:
        """Verify status command executes and prints header."""
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["status"])
        self.assertEqual(code, 0)
        self.assertIn("NotebookLM Batch Studio", out.getvalue())

    def test_cli_resume(self) -> None:
        """Verify resume command executes."""
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["resume"])
        self.assertEqual(code, 0)
        self.assertIn("已手動喚醒", out.getvalue())


if __name__ == "__main__":
    unittest.main()

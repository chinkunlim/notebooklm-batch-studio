"""Unit and integration tests for FastAPI REST endpoints, OpenAPI docs, and MCP server tools.

Verifies HTTP status codes, Host/CORS security middleware, path traversal protections,
and MCP confirmation parameter semantics.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from starlette.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course, Lecture, ProfileName
from notebooklm_batch_studio.domain.repositories import NotebookLMClientProtocol
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.study_service import StudyTrackerService


class MockNotebookLMClient(NotebookLMClientProtocol):
    """Offline test stub for NotebookLM operations."""

    def __init__(self) -> None:
        """Initialize mock client."""
        self.created_notebooks: list[str] = []

    def check_auth(self) -> bool:
        """Return fake authenticated status."""
        return True

    async def create_notebook(self, title: str) -> str:
        """Create mock notebook."""
        return "mock-nb-api-test"

    async def upload_source(self, notebook_id: str, file_path: str) -> str:
        """Upload mock source."""
        return f"src-{Path(file_path).stem}"

    async def wait_source_ready(self, notebook_id: str, source_id: str, timeout_seconds: int = 60) -> None:
        """Mock source ready wait."""
        return

    async def generate_audio(self, notebook_id: str, source_ids: list[str]) -> str:
        """Mock generate audio."""
        return "audio-job-1"

    async def download_audio(self, notebook_id: str, output_path: str) -> None:
        """Mock download audio."""
        Path(output_path).write_bytes(b"ID3mockaudio")

    async def generate_quiz(self, notebook_id: str, source_ids: list[str], prompt: str = "") -> str:
        """Mock generate quiz."""
        return "quiz-job-1"

    async def download_quiz(self, notebook_id: str, output_path: str) -> None:
        """Mock download quiz."""
        Path(output_path).write_text("{}", encoding="utf-8")

    async def generate_flashcards(self, notebook_id: str, source_ids: list[str]) -> str:
        """Mock generate flashcards."""
        return "fc-job-1"

    async def download_flashcards(self, notebook_id: str, output_path: str) -> None:
        """Mock download flashcards."""
        Path(output_path).write_text("[]", encoding="utf-8")

    async def generate_mind_map(self, notebook_id: str, source_ids: list[str]) -> str:
        """Mock generate mind map."""
        return "mm-job-1"

    async def download_mind_map(self, notebook_id: str, output_path: str) -> None:
        """Mock download mind map."""
        Path(output_path).write_text("{}", encoding="utf-8")

    async def rename_artifact(self, notebook_id: str, artifact_id: str, title: str) -> None:
        """Mock rename artifact."""
        pass

    async def generate_report(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Mock generate report."""
        return "report-job-1"

    async def download_report(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download report."""
        Path(output_path).write_text("# Report", encoding="utf-8")

    async def generate_slide_deck(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Mock generate slide deck."""
        return "slide-job-1"

    async def download_slide_deck(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download slide deck."""
        Path(output_path).write_text("# Slide Deck", encoding="utf-8")

    async def generate_infographic(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Mock generate infographic."""
        return "info-job-1"

    async def download_infographic(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download infographic."""
        Path(output_path).write_bytes(b"PNG")

    async def generate_data_table(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Mock generate data table."""
        return "dt-job-1"

    async def download_data_table(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download data table."""
        Path(output_path).write_text("| A | B |", encoding="utf-8")

    async def generate_video(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Mock generate video."""
        return "video-job-1"

    async def download_video(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Mock download video."""
        Path(output_path).write_bytes(b"MP4")

    async def find_latest_artifact(self, notebook_id: str, artifact_type: str | None = None) -> str | None:
        """Mock find latest artifact."""
        return "mock-artifact-id-api"

    async def list_artifacts(self, notebook_id: str) -> list[dict[str, Any]]:
        """Mock list remote artifacts."""
        return [{"id": "remote-art-1", "title": "[Ch01] Remote Quiz", "kind": "quiz", "is_completed": True}]

    async def download_artifact_by_kind(
        self, notebook_id: str, artifact_id: str, kind: str, output_path: str
    ) -> str:
        """Mock download remote artifact by kind."""
        Path(output_path).write_text("{}", encoding="utf-8")
        return output_path


class TestApiAndMcp(unittest.TestCase):
    """Test suite for HTTP REST API and MCP Tool Server."""

    def setUp(self) -> None:
        """Set up in-memory SQLite database, mock service, and test client."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        (self.data_dir / "output" / "courses" / "BIO101" / "01_Membranes").mkdir(parents=True)

        self.config = AppConfig(
            app_env="test",
            log_level="DEBUG",
            log_to_file=False,
            data_dir=self.data_dir,
            database_url="sqlite://",
            http_host="127.0.0.1",
            http_port=8768,
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
            http_allowed_origins=("http://127.0.0.1:8768", "http://127.0.0.1:8080"),
        )

        self.engine = create_db_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = session_scope(self.engine).__enter__()

        self.course_repo = CourseRepository(self.session)
        self.queue_repo = QueueRepository(self.session)
        self.study_repo = StudyRepository(self.session)
        self.client_mock = MockNotebookLMClient()

        self.service = BatchStudioService(
            course_repo=self.course_repo,
            queue_repo=self.queue_repo,
            notebooklm_client=self.client_mock,
            config=self.config,
        )
        self.study_service = StudyTrackerService(study_repo=self.study_repo, config=self.config)

        # Seed initial test course
        self.course = Course(
            code="BIO101",
            name="細胞生物學",
            source_dir=str(self.data_dir),
            notebook_id="mock-nb-123",
            profile=ProfileName.FULL,
            lectures=[
                Lecture(no=1, topic="細胞膜", filename="01_Membranes.pdf", sha256="abc1"),
                Lecture(no=2, topic="酵素作用", filename="02_Enzymes.pdf", sha256="abc2"),
            ],
        )
        self.course_repo.save_course(self.course)
        self.service.enqueue_course_artifacts("BIO101")

        # Create dummy output files for artifact tests
        quiz_dir = self.data_dir / "output" / "courses" / "BIO101" / "01_細胞膜"
        quiz_dir.mkdir(parents=True, exist_ok=True)
        (quiz_dir / "題目卷.md").write_text("# 題目卷\n1. 什麼是細胞膜？", encoding="utf-8")
        (quiz_dir / "答案卷.md").write_text("# 答案卷\n1. 雙層磷脂質", encoding="utf-8")
        (quiz_dir / "quiz.json").write_text(json.dumps({"questions": []}), encoding="utf-8")
        (quiz_dir / "sample.pdf").write_bytes(b"%PDF-1.4 test")

        self.app = create_app(config=self.config, service=self.service, study_service=self.study_service)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        """Tear down database session and temporary directory."""
        self.session.close()
        self.temp_dir.cleanup()

    def test_get_dashboard_html(self) -> None:
        """GET / returns the local management dashboard HTML."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("NotebookLM Batch Studio", resp.text)
        self.assertIn("127.0.0.1:8768", resp.text)

    def test_get_status_endpoint(self) -> None:
        """GET /api/status returns application environment, auth status, and queue counts."""
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["app_env"], "test")
        self.assertTrue(data["auth"]["authenticated"])
        self.assertEqual(data["total_courses"], 1)

    def test_list_and_get_courses(self) -> None:
        """GET /api/courses and /api/courses/{code} return accurate course structure."""
        resp = self.client.get("/api/courses")
        self.assertEqual(resp.status_code, 200)
        courses = resp.json()
        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["code"], "BIO101")
        self.assertEqual(courses[0]["lecture_count"], 2)

        resp_detail = self.client.get("/api/courses/BIO101")
        self.assertEqual(resp_detail.status_code, 200)
        detail = resp_detail.json()
        self.assertEqual(detail["code"], "BIO101")
        self.assertEqual(len(detail["lectures"]), 2)
        self.assertTrue(len(detail["jobs"]) > 0)

        resp_404 = self.client.get("/api/courses/NONEXISTENT")
        self.assertEqual(resp_404.status_code, 404)

    def test_preview_and_add_courses_api(self) -> None:
        """POST /api/courses/preview and /api/courses scan and register folder."""
        # Create a temporary course folder with sample PDF
        course_folder = self.data_dir / "CS101"
        course_folder.mkdir()
        (course_folder / "01_Algorithms.pdf").write_bytes(b"%PDF dummy")

        resp_preview = self.client.post("/api/courses/preview", json={"folders": [str(course_folder)]})
        self.assertEqual(resp_preview.status_code, 200)
        preview_data = resp_preview.json()
        self.assertEqual(len(preview_data), 1)
        self.assertTrue(preview_data[0]["is_valid"])
        self.assertEqual(preview_data[0]["course_code"], "CS101")

        resp_add = self.client.post(
            "/api/courses",
            json={"folders": [str(course_folder)], "profile": "quiz-only"},
        )
        self.assertEqual(resp_add.status_code, 200)
        added_data = resp_add.json()
        self.assertEqual(len(added_data), 1)
        self.assertEqual(added_data[0]["code"], "CS101")
        self.assertEqual(added_data[0]["profile"], "quiz-only")

    def test_quiz_and_artifact_download(self) -> None:
        """GET /api/courses/{code}/lectures/{no}/quiz/{variant} and artifact file download."""
        resp_quiz = self.client.get(
            "/api/courses/BIO101/lectures/1/quiz/1-基礎",
            params={"with_answers": "false"},
        )
        self.assertEqual(resp_quiz.status_code, 200)
        quiz_data = resp_quiz.json()
        self.assertIn("題目卷", quiz_data["markdown"])

        # Artifact listing
        resp_artifacts = self.client.get("/api/courses/BIO101/artifacts")
        self.assertEqual(resp_artifacts.status_code, 200)
        files = resp_artifacts.json()
        self.assertTrue(any(f["filename"] == "sample.pdf" for f in files))

        # Download artifact
        resp_download = self.client.get("/api/artifacts/BIO101/download/01_細胞膜/sample.pdf")
        self.assertEqual(resp_download.status_code, 200)
        self.assertEqual(resp_download.content, b"%PDF-1.4 test")

    def test_path_traversal_prevention(self) -> None:
        """Security: Attempting directory traversal returns 403 Forbidden."""
        resp = self.client.get("/api/artifacts/BIO101/download/../../../../etc/passwd")
        self.assertIn(resp.status_code, (403, 404))

    def test_untrusted_host_rejection(self) -> None:
        """Security: Requests with an unauthorized Host header are rejected with 400 Bad Request."""
        resp = self.client.get("/api/status", headers={"Host": "untrusted-attacker.com"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.text, "Untrusted Host header")

    def test_queue_control_endpoints(self) -> None:
        """POST queue controls: /api/queue/start, /pause, /resume, and /jobs/{id}/retry."""
        resp_start = self.client.post("/api/queue/start")
        self.assertEqual(resp_start.status_code, 200)
        self.assertTrue(resp_start.json()["success"])

        resp_pause = self.client.post("/api/queue/pause")
        self.assertEqual(resp_pause.status_code, 200)
        self.assertTrue(resp_pause.json()["success"])

        resp_resume = self.client.post("/api/queue/resume")
        self.assertEqual(resp_resume.status_code, 200)

        # Retry valid job
        jobs = self.queue_repo.list_jobs(course_code="BIO101")
        self.assertTrue(len(jobs) > 0)
        job_id = jobs[0].id
        resp_retry = self.client.post(f"/api/jobs/{job_id}/retry")
        self.assertEqual(resp_retry.status_code, 200)
        self.assertTrue(resp_retry.json()["success"])

    def test_mcp_server_tools(self) -> None:
        """Verify MCP tools registration, query responses, and confirm safety protocol."""
        mcp = build_mcp_server(service=self.service, study_service=self.study_service, config=self.config)

        # list_courses
        list_fn = mcp._tool_manager._tools["list_courses"].fn  # type: ignore[attr-defined]
        res_list = json.loads(list_fn())
        self.assertEqual(len(res_list), 1)
        self.assertEqual(res_list[0]["code"], "BIO101")

        # get_course_status
        status_fn = mcp._tool_manager._tools["get_course_status"].fn  # type: ignore[attr-defined]
        res_status = json.loads(status_fn("BIO101"))
        self.assertEqual(res_status["code"], "BIO101")

        # get_quiz
        quiz_fn = mcp._tool_manager._tools["get_quiz"].fn  # type: ignore[attr-defined]
        res_quiz = quiz_fn("BIO101", 1, "1-基礎", False)
        self.assertIn("題目卷", res_quiz)

        # add_courses without confirm
        add_fn = mcp._tool_manager._tools["add_courses"].fn  # type: ignore[attr-defined]
        res_unconfirmed = json.loads(add_fn(["/dummy/path"], "full", False))
        self.assertFalse(res_unconfirmed["confirmed"])
        self.assertIn("warning", res_unconfirmed)

        # retry_item without confirm
        retry_fn = mcp._tool_manager._tools["retry_item"].fn  # type: ignore[attr-defined]
        res_retry_unconfirmed = retry_fn("job-123", False)
        self.assertIn("Action not confirmed", res_retry_unconfirmed)

        # start_queue and pause_queue without confirm
        start_fn = mcp._tool_manager._tools["start_queue"].fn  # type: ignore[attr-defined]
        self.assertIn("Action not confirmed", start_fn(False))
        self.assertIn("started successfully", start_fn(True))

        # Study tools verification
        self.study_service.record_quiz_attempt(
            course_code="BIO101",
            lecture_no=1,
            quiz_variant="academic",
            score=9,
            total_questions=10,
            mistakes_data=[
                {
                    "question_text": "What is ATP?",
                    "choices": ["Energy", "DNA", "Protein", "Lipid"],
                    "correct_index": 0,
                    "selected_index": 1,
                    "explanation": "ATP is the energy currency.",
                }
            ],
        )

        history_fn = mcp._tool_manager._tools["get_study_history"].fn  # type: ignore[attr-defined]
        history_res = json.loads(history_fn("BIO101"))
        self.assertEqual(len(history_res), 1)
        self.assertEqual(history_res[0]["score"], 9)

        weak_fn = mcp._tool_manager._tools["get_weaknesses"].fn  # type: ignore[attr-defined]
        weak_res = json.loads(weak_fn("BIO101"))
        self.assertEqual(len(weak_res), 1)
        self.assertEqual(weak_res[0]["question_text"], "What is ATP?")

        resolve_fn = mcp._tool_manager._tools["resolve_weakness_mistake"].fn  # type: ignore[attr-defined]
        unconf_resolve = resolve_fn("fake-id", False)
        self.assertIn("Action not confirmed", unconf_resolve)

        # Sync and prompt tools verification
        sync_fn = mcp._tool_manager._tools["sync_course_remote_artifacts"].fn  # type: ignore[attr-defined]
        import asyncio

        sync_unconf = asyncio.run(sync_fn("BIO101", False))
        self.assertIn("Action not confirmed", sync_unconf)

        refine_fn = mcp._tool_manager._tools["refine_prompts_with_ollama"].fn  # type: ignore[attr-defined]
        refine_unconf = refine_fn("BIO101", False)
        self.assertIn("Action not confirmed", refine_unconf)

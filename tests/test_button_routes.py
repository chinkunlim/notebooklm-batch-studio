"""Every button's API call must exist: job prompt routes, wake-quota button, HEAD downloads (button audit)."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course, Lecture
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

STATIC = Path(__file__).resolve().parents[1] / "src/notebooklm_batch_studio/entrypoints/static"


class ButtonRoutesTest(unittest.TestCase):
    """The prompt editor and the wake button call routes that exist and work."""

    def setUp(self) -> None:
        """Create database, course, one job and the HTTP client."""
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
            [
                ArtifactJob(
                    id="q",
                    course_code="BIO101",
                    lecture_no=1,
                    artifact_type=ArtifactType.QUIZ_1,
                    custom_prompt="生成 30 題",
                )
            ]
        )
        self.http = TestClient(
            create_app(config=self.config, service=self.service, study_service=mock.MagicMock())
        )

    def tearDown(self) -> None:
        """Close the session and remove temporary files."""
        self.session.close()
        self.tmpdir.cleanup()

    def test_job_prompt_view_and_edit(self) -> None:
        """GET shows the prompt sent to Gemini Notebook; POST saves a new one; unknown jobs are 404."""
        self.assertEqual(self.http.get("/api/jobs/q/prompt").json()["custom_prompt"], "生成 30 題")
        self.assertEqual(self.http.post("/api/jobs/q/prompt", json={"prompt": "生成 20 題"}).status_code, 200)
        self.assertEqual(self.queue_repo.get_job("q").custom_prompt, "生成 20 題")  # type: ignore[union-attr]
        self.assertEqual(self.http.get("/api/jobs/missing/prompt").status_code, 404)
        self.assertEqual(self.http.post("/api/jobs/missing/prompt", json={"prompt": "x"}).status_code, 404)

    def test_job_prompt_mcp_tools(self) -> None:
        """MCP can read a prompt; changing it needs confirm=True."""
        mcp = build_mcp_server(service=self.service, study_service=mock.MagicMock(), config=self.config)
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        self.assertEqual(json.loads(tools["get_job_prompt"].fn("q"))["custom_prompt"], "生成 30 題")
        self.assertFalse(json.loads(tools["set_job_prompt"].fn("q", "新的"))["confirmed"])
        self.assertTrue(json.loads(tools["set_job_prompt"].fn("q", "新的", confirm=True))["success"])
        self.assertEqual(self.queue_repo.get_job("q").custom_prompt, "新的")  # type: ignore[union-attr]

    def test_download_answers_head(self) -> None:
        """HEAD on a download says whether an optional file exists (infographic device versions)."""
        folder = self.config.courses_output_dir / "BIO101" / "01_a"
        folder.mkdir(parents=True)
        (folder / "infographic_A4.pdf").write_bytes(b"%PDF-1.4")
        url = "/api/artifacts/BIO101/download/01_a/infographic_A4.pdf"
        self.assertEqual(self.http.head(url).status_code, 200)
        self.assertEqual(self.http.head(url.replace("A4", "iPadAir4")).status_code, 404)

    def test_every_fixed_api_path_in_the_page_exists(self) -> None:
        """Each literal '/api/...' path the page fetches is a real route (catches buttons that 404)."""
        routes = set(self.http.app.openapi()["paths"])  # type: ignore[attr-defined]
        # Both sides use X for a variable segment; a page X may stand for a fixed word ("pause").
        normalized = {re.sub(r"\{[^}]+\}", "X", p) for p in routes}
        page = "".join(p.read_text(encoding="utf-8") for p in STATIC.glob("*.js")) + (
            STATIC / "index.html"
        ).read_text(encoding="utf-8")
        missing = []
        for raw in re.findall(r"fetch\(\s*[`'\"](/api/[^`'\"?]*)", page):
            # `${...}` placeholders become one segment; one cut off by a quote inside it too.
            path = re.sub(r"\$\{[^}]*$", "X", re.sub(r"\$\{[^}]+\}", "X", raw))
            pattern = re.compile("^" + re.escape(path).replace("X", "[^/]+") + "$")
            if not any(pattern.match(r) for r in normalized):
                missing.append(raw)
        self.maxDiff = None
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()

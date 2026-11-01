"""Tests for TASK-008 quota visibility, per-notebook source limits, and CLI `batch --profile`."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import SourceLimitExceededError
from notebooklm_batch_studio.domain.models import Course, Lecture, ProfileName
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.cli import main
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

QUOTA = {"status": "ready", "windows": [], "actions": [], "notebook_limit": 100, "source_limit": 2}


class LimitClient:
    """Minimal NotebookLM client fake for limit and quota tests."""

    def __init__(self, source_limit: int | None) -> None:
        """Initialize the fake.

        Args:
            source_limit: Value returned by get_source_limit.
        """
        self.source_limit = source_limit
        self.notebooks_created: list[str] = []
        self.uploads: list[str] = []

    async def get_source_limit(self) -> int | None:
        """Return the configured source limit.

        Returns:
            Source limit or None.
        """
        return self.source_limit

    async def get_quota_status(self) -> dict[str, Any]:
        """Return a fixed quota summary.

        Returns:
            Quota dictionary.
        """
        return QUOTA

    async def create_notebook(self, title: str) -> str:
        """Record notebook creation.

        Args:
            title: Notebook title.

        Returns:
            Fake notebook id.
        """
        self.notebooks_created.append(title)
        return "nb-1"

    async def upload_source(self, notebook_id: str, file_path: str) -> str:
        """Record an upload.

        Args:
            notebook_id: Notebook id.
            file_path: PDF path.

        Returns:
            Fake source id.
        """
        self.uploads.append(file_path)
        return f"src-{len(self.uploads)}"

    async def wait_source_ready(self, notebook_id: str, source_id: str, timeout_seconds: int = 180) -> None:
        """No-op readiness wait.

        Args:
            notebook_id: Notebook id.
            source_id: Source id.
            timeout_seconds: Ignored.
        """


class QuotaAndLimitTest(unittest.IsolatedAsyncioTestCase):
    """Source-limit guard and quota exposure across service, HTTP, and MCP."""

    def setUp(self) -> None:
        """Create a three-lecture course in an in-memory database."""
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        for name in ("01_a.pdf", "02_b.pdf", "03_c.pdf"):
            (tmp / name).write_bytes(b"%PDF-1.4")
        self.config = AppConfig(
            data_dir=tmp / "data",
            notebooklm_home=tmp / "cfg",
            log_to_file=False,
            http_allowed_hosts=("testserver",),
        )
        self.engine = create_db_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = session_scope(self.engine).__enter__()
        self.course_repo = CourseRepository(self.session)
        self.course_repo.save_course(
            Course(
                code="BIO101",
                name="細胞生物學",
                source_dir=str(tmp),
                lectures=[
                    Lecture(no=i, topic=t, filename=f, sha256=t)
                    for i, (f, t) in enumerate((("01_a.pdf", "a"), ("02_b.pdf", "b"), ("03_c.pdf", "c")), 1)
                ],
            )
        )

    def tearDown(self) -> None:
        """Close the session and remove temporary files."""
        self.session.close()
        self.tmpdir.cleanup()

    def _service(self, client: LimitClient) -> BatchStudioService:
        """Build the service under test.

        Args:
            client: Fake NotebookLM client.

        Returns:
            BatchStudioService.
        """
        return BatchStudioService(
            self.course_repo,
            QueueRepository(self.session),
            client,  # type: ignore[arg-type]
            self.config,
        )

    async def test_setup_refuses_course_over_source_limit_before_any_upload(self) -> None:
        """Three lectures with a limit of 2 fail fast: no notebook, no uploads."""
        client = LimitClient(source_limit=2)
        with self.assertRaises(SourceLimitExceededError) as ctx:
            await self._service(client).setup_notebook_and_sources("BIO101")
        self.assertIn("3", str(ctx.exception))
        self.assertEqual(client.notebooks_created, [])
        self.assertEqual(client.uploads, [])

    async def test_setup_proceeds_when_limit_unknown_or_enough(self) -> None:
        """An unknown (None) or sufficient limit lets setup upload every lecture."""
        for limit in (None, 3):
            client = LimitClient(source_limit=limit)
            self.course_repo.update_notebook_id("BIO101", "")
            await self._service(client).setup_notebook_and_sources("BIO101")
            self.assertEqual(len(client.uploads), 3, f"limit={limit}")
            for no in (1, 2, 3):
                self.course_repo.update_lecture_source_id("BIO101", no, "")

    async def test_service_returns_quota_status(self) -> None:
        """The service passes the adapter's quota summary through."""
        self.assertEqual(await self._service(LimitClient(2)).get_notebooklm_quota(), QUOTA)

    def test_http_and_mcp_expose_quota(self) -> None:
        """GET /api/notebooklm/quota and the MCP tool both return the quota summary."""
        service = self._service(LimitClient(2))
        app = create_app(config=self.config, service=service, study_service=mock.MagicMock())
        resp = TestClient(app).get("/api/notebooklm/quota")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["source_limit"], 2)

        mcp = build_mcp_server(service=service, study_service=mock.MagicMock(), config=self.config)
        tool = mcp._tool_manager._tools["get_notebooklm_quota"].fn  # type: ignore[attr-defined]
        import asyncio

        self.assertEqual(json.loads(asyncio.run(tool()))["notebook_limit"], 100)


class CliProfileTest(unittest.TestCase):
    """`batch --profile` must register the course with the chosen profile."""

    def test_batch_profile_is_applied(self) -> None:
        """quiz-only is stored on the course instead of the default full profile."""
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            course_dir = tmp / "BIO101 細胞生物學"
            course_dir.mkdir()
            (course_dir / "01_a.pdf").write_bytes(b"%PDF-1.4")
            db_url = f"sqlite:///{tmp / 'app.db'}"
            cfg = AppConfig(data_dir=tmp / "data", database_url=db_url, log_to_file=False)
            Base.metadata.create_all(create_db_engine(db_url))

            with (
                mock.patch("notebooklm_batch_studio.entrypoints.cli.load_config", return_value=cfg),
                mock.patch(
                    "notebooklm_batch_studio.entrypoints.cli._execute_batch_pipeline", mock.AsyncMock()
                ),
                redirect_stdout(io.StringIO()),
            ):
                code = main(["batch", str(course_dir), "--profile", "quiz-only"])

            self.assertEqual(code, 0)
            with session_scope(create_db_engine(db_url)) as session:
                course = CourseRepository(session).get_course("BIO101")
            assert course is not None
            self.assertEqual(course.profile, ProfileName.QUIZ_ONLY)


if __name__ == "__main__":
    unittest.main()

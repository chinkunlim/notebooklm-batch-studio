"""Offline unit tests for reverse-importing remote Gemini Notebooks and downloading all files locally."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course, Lecture
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.reverse_import import ReverseImportOptions, ReverseImportService
from tests.dummy_client import DummyStudioClient


class TestReverseImport(unittest.TestCase):
    """Verify reverse import service, HTTP endpoints, and MCP tools offline."""

    def setUp(self) -> None:
        """Set up temporary SQLite DB, DATA_DIR, DummyStudioClient, HTTP client, and MCP server."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.config = AppConfig(
            data_dir=self.tmp / "data",
            notebooklm_home=self.tmp / "cfg",
            log_to_file=False,
            http_allowed_hosts=("testserver",),
        )
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session_ctx = session_scope(engine)
        self.session = self.session_ctx.__enter__()
        self.course_repo = CourseRepository(self.session)
        self.queue_repo = QueueRepository(self.session)
        self.dummy = DummyStudioClient()
        self.dummy._notebooks = [
            {"id": "nb-remote-1", "title": "Linear Algebra", "sources_count": 2, "is_owner": True},
            {"id": "nb-linked-1", "title": "Linked Bio", "sources_count": 1, "is_owner": True},
        ]
        self.dummy._sources["nb-remote-1"] = [
            {
                "id": "src-1",
                "title": "Ch01 Vectors.pdf",
                "status": "ready",
                "kind": "pdf",
                "content": "Vector space notes.",
            },
            {
                "id": "src-2",
                "title": "Ch02 Matrices.pdf",
                "status": "ready",
                "kind": "pdf",
                "content": "Matrix algebra notes.",
            },
        ]
        self.dummy._sources["nb-linked-1"] = [
            {
                "id": "src-b1",
                "title": "Bio Intro.pdf",
                "status": "ready",
                "kind": "pdf",
                "content": "Cell biology overview.",
            },
        ]
        self.dummy._artifacts = {
            "nb-remote-1": [
                {"id": "art-r1", "title": "[Ch01] Briefing", "kind": "report", "status": "completed"},
            ],
            "nb-linked-1": [
                {"id": "art-b1", "title": "[Ch01] Audio", "kind": "audio", "status": "completed"},
            ],
        }

        self.course_repo.save_course(
            Course(
                code="BIO101",
                name="Linked Bio",
                source_dir=str(self.tmp / "bio_src"),
                notebook_id="nb-linked-1",
                lectures=[
                    Lecture(no=1, topic="Intro", filename="Bio Intro.pdf", sha256="abc", source_id="src-b1")
                ],
            )
        )
        self.service = BatchStudioService(self.course_repo, self.queue_repo, self.dummy, self.config)
        self.app = create_app(config=self.config, service=self.service)
        self.client = TestClient(self.app)
        self.mcp = build_mcp_server(service=self.service, config=self.config)

    def tearDown(self) -> None:
        """Close DB session and remove temporary directory."""
        self.session_ctx.__exit__(None, None, None)
        self.tmpdir.cleanup()

    def test_list_and_preview_remote_notebooks_http(self) -> None:
        """HTTP GET endpoints list notebooks with link status and preview sources/artifacts."""
        res = self.client.get("/api/remote-notebooks")
        self.assertEqual(res.status_code, 200)
        nbs = {n["id"]: n for n in res.json()["notebooks"]}
        self.assertIsNone(nbs["nb-remote-1"]["linked_course_code"])
        self.assertEqual(nbs["nb-linked-1"]["linked_course_code"], "BIO101")

        prev = self.client.get("/api/remote-notebooks/nb-remote-1/preview")
        self.assertEqual(prev.status_code, 200)
        body = prev.json()
        self.assertEqual(len(body["sources"]), 2)
        self.assertEqual(len(body["artifacts"]), 1)

    def test_import_remote_notebook_downloads_sources_and_artifacts(self) -> None:
        """Reverse import creates Course, saves Markdown sources locally, and syncs artifacts."""
        res = self.client.post(
            "/api/remote-notebooks/nb-remote-1/import",
            json={"course_code": "MATH201", "download_sources": True, "download_artifacts": True},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["course_code"], "MATH201")
        self.assertEqual(data["downloaded_sources_count"], 2)
        self.assertEqual(data["synced_artifacts_count"], 1)

        saved_course = self.course_repo.get_course("MATH201")
        self.assertIsNotNone(saved_course)
        assert saved_course is not None
        self.assertEqual(saved_course.notebook_id, "nb-remote-1")
        self.assertEqual(len(saved_course.lectures), 2)
        for src in data["downloaded_sources"]:
            self.assertTrue(Path(src["path"]).exists())
            self.assertIn("notes.", Path(src["path"]).read_text(encoding="utf-8"))

    def test_download_all_course_files_locally_http(self) -> None:
        """POST /api/courses/{code}/download-all downloads both remote sources and artifacts."""
        res = self.client.post(
            "/api/courses/BIO101/download-all",
            json={"include_sources": True, "include_artifacts": True},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["downloaded_sources_count"], 1)
        self.assertEqual(data["synced_artifacts_count"], 1)
        self.assertTrue(Path(data["downloaded_sources"][0]["path"]).exists())

    def test_mcp_reverse_import_requires_confirmation_and_executes(self) -> None:
        """MCP tools require confirm=True for mutating imports/downloads and execute when confirmed."""

        async def _run() -> None:
            tools = self.mcp._tool_manager._tools  # type: ignore[attr-defined]
            nbs = json.loads(await tools["list_remote_notebooks"].fn())
            self.assertEqual(len(nbs), 2)

            guard_imp = json.loads(await tools["import_remote_notebook"].fn("nb-remote-1", confirm=False))
            self.assertTrue(guard_imp["requires_confirmation"])

            imp_data = json.loads(
                await tools["import_remote_notebook"].fn("nb-remote-1", course_code="MATH202", confirm=True)
            )
            self.assertEqual(imp_data["course_code"], "MATH202")
            self.assertEqual(imp_data["downloaded_sources_count"], 2)

            guard_dl = json.loads(await tools["download_course_files_locally"].fn("BIO101", confirm=False))
            self.assertTrue(guard_dl["requires_confirmation"])

            dl_data = json.loads(await tools["download_course_files_locally"].fn("BIO101", confirm=True))
            self.assertEqual(dl_data["downloaded_sources_count"], 1)

        asyncio.run(_run())

    def test_reverse_import_service_respects_source_subset(self) -> None:
        """ReverseImportService downloads only selected source_ids when specified."""
        svc = ReverseImportService(
            notebooklm_client=self.dummy,
            course_repo=self.course_repo,
            queue_repo=self.queue_repo,
            output_base_dir=self.config.output_dir,
        )
        res = asyncio.run(
            svc.import_remote_notebook(
                ReverseImportOptions(
                    notebook_id="nb-remote-1",
                    course_code="MATH_SUB",
                    download_sources=True,
                    download_artifacts=False,
                    source_ids=["src-1"],
                )
            )
        )
        self.assertEqual(res["downloaded_sources_count"], 1)
        self.assertEqual(res["synced_artifacts_count"], 0)

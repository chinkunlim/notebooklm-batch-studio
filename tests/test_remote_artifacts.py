"""Tests for remote artifact listing (active version flagging) and safe deletion (HTTP & MCP)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course, Lecture
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.study_service import StudyTrackerService
from tests.dummy_client import DummyStudioClient


class _RemoteArtifactDummyClient(DummyStudioClient):
    """Dummy client returning two versions of a remote artifact."""

    async def list_artifacts(self, notebook_id: str) -> list[dict[str, Any]]:
        """Return v1 and v2 remote quiz artifacts."""
        return [
            {"id": "art-v1", "title": "[Ch01] Quiz 1", "kind": "quiz"},
            {"id": "art-v2", "title": "[Ch01] Quiz 1 (v2)", "kind": "quiz"},
        ]


class TestRemoteArtifactsAdmin(unittest.IsolatedAsyncioTestCase):
    """Verify active-version annotation and deletion for remote artifacts."""

    def setUp(self) -> None:
        """Create isolated DB, course with v1/v2 jobs, HTTP client, and MCP server."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.config = AppConfig(
            data_dir=self.tmp / "data", log_to_file=False, http_allowed_hosts=("testserver",)
        )
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session = session_scope(engine).__enter__()
        c_repo = CourseRepository(self.session)
        q_repo = QueueRepository(self.session)
        s_repo = StudyRepository(self.session)
        c_repo.save_course(
            Course(
                code="BIO101",
                name="Biology",
                source_dir=str(self.tmp),
                notebook_id="nb-1",
                lectures=[Lecture(no=1, topic="Ch01", filename="Ch01.pdf", sha256="abc")],
            )
        )
        out_dir = self.config.courses_output_dir / "BIO101" / "01_Ch01"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "quiz_1_v2.json").write_text("{}", encoding="utf-8")
        q_repo.enqueue_jobs(
            [
                ArtifactJob(
                    id="job-v1",
                    course_code="BIO101",
                    lecture_no=1,
                    artifact_type=ArtifactType.QUIZ_1,
                    version=1,
                ),
                ArtifactJob(
                    id="job-v2",
                    course_code="BIO101",
                    lecture_no=1,
                    artifact_type=ArtifactType.QUIZ_1,
                    version=2,
                ),
            ]
        )
        q_repo.complete_job("job-v1", "01_Ch01/quiz_1.json")
        q_repo.record_artifact_ids("job-v1", ["art-v1"])
        q_repo.complete_job("job-v2", "01_Ch01/quiz_1_v2.json")
        q_repo.record_artifact_ids("job-v2", ["art-v2"])
        self.client = _RemoteArtifactDummyClient()
        self.service = BatchStudioService(c_repo, q_repo, self.client, self.config)
        self.study = StudyTrackerService(s_repo, config=self.config)
        app = create_app(config=self.config, service=self.service, study_service=self.study)
        self.http = TestClient(app)
        self.mcp = build_mcp_server(config=self.config, service=self.service, study_service=self.study)

    def tearDown(self) -> None:
        """Close DB session and remove temp directory."""
        self.session.close()
        self.tmpdir.cleanup()

    def test_http_list_marks_latest_active_and_delete_cleans_local(self) -> None:
        """GET remote-artifacts flags v2 as is_latest_active and DELETE removes remote + local."""
        res = self.http.get("/api/courses/BIO101/remote-artifacts")
        self.assertEqual(res.status_code, 200)
        arts = {a["id"]: a for a in res.json()["artifacts"]}
        self.assertFalse(arts["art-v1"]["is_latest_active"])
        self.assertTrue(arts["art-v2"]["is_latest_active"])
        self.assertEqual(arts["art-v2"]["local_version"], 2)

        del_res = self.http.delete(
            "/api/courses/BIO101/remote-artifacts/art-v2", params={"delete_local": "true"}
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertIn("delete_artifact:nb-1:art-v2", self.client.calls)
        self.assertFalse((self.config.courses_output_dir / "BIO101" / "01_Ch01" / "quiz_1_v2.json").exists())

    async def test_mcp_remote_artifacts_requires_confirm(self) -> None:
        """MCP delete_remote_artifact requires confirm=True before deleting."""
        tools = self.mcp._tool_manager._tools  # type: ignore[attr-defined]
        blocked = json.loads(await tools["delete_remote_artifact"].fn("BIO101", "art-v1", confirm=False))
        self.assertTrue(blocked["requires_confirmation"])
        done = json.loads(await tools["delete_remote_artifact"].fn("BIO101", "art-v1", confirm=True))
        self.assertEqual(done["deleted_artifact_id"], "art-v1")

    async def test_advanced_remote_artifact_endpoints_and_mcp(self) -> None:
        """Verify suggest-reports, cinematic-video, revise-slide, export, and retry routes + MCP."""
        sug = self.http.get("/api/courses/BIO101/remote-artifacts/suggest-reports")
        self.assertEqual(sug.status_code, 200)
        self.assertEqual(len(sug.json()["suggestions"]), 1)

        vid = self.http.post(
            "/api/courses/BIO101/remote-artifacts/cinematic-video", json={"instructions": "重點"}
        )
        self.assertEqual(vid.status_code, 200)
        self.assertEqual(vid.json()["artifact_id"], "art-cinematic-1")

        rev = self.http.post(
            "/api/courses/BIO101/remote-artifacts/art-v2/revise-slide",
            json={"slide_index": 0, "prompt": "簡化圖表"},
        )
        self.assertEqual(rev.status_code, 200)

        exp = self.http.post(
            "/api/courses/BIO101/remote-artifacts/art-v2/export",
            json={"title": "BIO101 彙整", "kind": "data_table"},
        )
        self.assertEqual(exp.status_code, 200)

        ret = self.http.post("/api/courses/BIO101/remote-artifacts/art-v2/retry")
        self.assertEqual(ret.status_code, 200)

        tools = self.mcp._tool_manager._tools  # type: ignore[attr-defined]
        self.assertTrue(
            json.loads(await tools["generate_cinematic_video"].fn("BIO101", confirm=False))[
                "requires_confirmation"
            ]
        )
        mc_vid = json.loads(
            await tools["generate_cinematic_video"].fn("BIO101", instructions="核心", confirm=True)
        )
        self.assertEqual(mc_vid["artifact_id"], "art-cinematic-1")

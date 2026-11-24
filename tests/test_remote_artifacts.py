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
        self.assertFalse(blocked["confirmed"])
        self.assertIn("confirm", blocked["warning"].lower())
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
        vid_guard = json.loads(await tools["generate_cinematic_video"].fn("BIO101", confirm=False))
        self.assertFalse(vid_guard["confirmed"])
        self.assertIn("confirm", vid_guard["warning"].lower())
        mc_vid = json.loads(
            await tools["generate_cinematic_video"].fn("BIO101", instructions="核心", confirm=True)
        )
        self.assertEqual(mc_vid["artifact_id"], "art-cinematic-1")

    async def test_sources_research_and_chat_configure_endpoints_and_mcp(self) -> None:
        """HTTP and MCP cover URL/text source import, web research, and chat config."""
        u = self.http.post("/api/courses/BIO101/sources/url", json={"url": "https://youtu.be/xyz"})
        t = self.http.post("/api/courses/BIO101/sources/text", json={"title": "N", "content": "Body"})
        self.assertEqual((u.status_code, t.status_code), (200, 200))

        res = self.http.post("/api/courses/BIO101/sources/research", json={"query": "ATP", "mode": "fast"})
        self.assertEqual(res.status_code, 200)
        imp = self.http.post(
            "/api/courses/BIO101/sources/research/import",
            json={"task_id": res.json()["task_id"], "sources": res.json()["sources"]},
        )
        self.assertEqual(imp.status_code, 200)
        self.assertEqual(imp.json()["imported_count"], 1)

        cfg = self.http.put(
            "/api/courses/BIO101/qa/configure",
            json={"goal": "learning_guide", "response_length": "shorter"},
        )
        self.assertEqual(cfg.status_code, 200)
        self.assertEqual(cfg.json()["goal"], "learning_guide")

        tools = self.mcp._tool_manager._tools  # type: ignore[attr-defined]
        for call in (
            await tools["add_url_source"].fn("BIO101", "https://a.b", confirm=False),
            await tools["add_text_source"].fn("BIO101", "T", "B", confirm=False),
            await tools["import_research_sources"].fn(
                "BIO101", "t1", [{"url": "https://a.b", "title": "A"}], confirm=False
            ),
        ):
            payload = json.loads(call)
            self.assertFalse(payload["confirmed"])
            self.assertIn("confirm", payload["warning"].lower())
        from notebooklm_batch_studio.entrypoints.schemas import ChatConfigureRequest

        chat_guard = json.loads(
            await tools["configure_notebook_chat"].fn("BIO101", ChatConfigureRequest(), confirm=False)
        )
        self.assertFalse(chat_guard["confirmed"])
        self.assertIn("confirm", chat_guard["warning"].lower())
        mc_res = json.loads(await tools["research_course_sources"].fn("BIO101", "ATP", mode="deep"))
        self.assertEqual(mc_res["task_id"], "res-task-1")
        mc_cfg = json.loads(
            await tools["configure_notebook_chat"].fn(
                "BIO101", ChatConfigureRequest(goal="learning_guide"), confirm=True
            )
        )
        self.assertEqual(mc_cfg["goal"], "learning_guide")

        custom_cfg = self.http.put(
            "/api/courses/BIO101/qa/configure",
            json={"goal": "custom", "response_length": "longer", "custom_prompt": "Act as tutor"},
        )
        self.assertEqual(custom_cfg.status_code, 200)
        self.assertEqual(custom_cfg.json()["custom_prompt"], "Act as tutor")

        scoped = self.http.post(
            "/api/courses/BIO101/remote-artifacts/generate",
            json={"kind": "custom_report", "source_ids": ["src-1"], "instructions": "重點彙整"},
        )
        self.assertEqual(scoped.status_code, 200)
        self.assertEqual(scoped.json()["source_count"], 1)

        from notebooklm_batch_studio.entrypoints.schemas import GenerateScopedArtifactRequest

        gen_guard = json.loads(
            await tools["generate_from_sources"].fn(
                "BIO101", GenerateScopedArtifactRequest(kind="audio"), confirm=False
            )
        )
        self.assertFalse(gen_guard["confirmed"])
        self.assertIn("confirm", gen_guard["warning"].lower())
        mc_gen = json.loads(
            await tools["generate_from_sources"].fn(
                "BIO101",
                GenerateScopedArtifactRequest(kind="custom_report", source_ids=["src-1"], instructions="A"),
                confirm=True,
            )
        )
        self.assertEqual(mc_gen["kind"], "custom_report")

"""HTTP API and MCP tool tests for Gemini Notebook Q&A notes and tags (SPEC-011)."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.notes_repository import QANoteRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course, Lecture
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.qa_notes_service import QANotesService
from tests.dummy_client import DummyStudioClient


class TestQANotesAPIAndMCP(unittest.TestCase):
    """Verify HTTP routes and MCP tools for exploratory Q&A and Markdown notes."""

    def setUp(self) -> None:
        """Configure temporary DB, dummy client, QANotesService, HTTP TestClient, and MCP server."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.folder = self.tmp / "BIO101"
        self.folder.mkdir()
        (self.folder / "Ch01-intro.pdf").write_bytes(b"%PDF-1.4 intro")

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
        self.notes_repo = QANoteRepository(self.session)
        self.dummy = DummyStudioClient()

        self.course_repo.save_course(
            Course(
                code="BIO101",
                name="細胞生物學",
                source_dir=str(self.folder),
                notebook_id="nb-1",
                lectures=[
                    Lecture(
                        no=1,
                        topic="intro",
                        filename="Ch01-intro.pdf",
                        sha256="1",
                        source_id="src-1",
                        upload_status="ready",
                    )
                ],
            )
        )
        self.service = BatchStudioService(self.course_repo, self.queue_repo, self.dummy, self.config)
        self.qa_notes = QANotesService(self.course_repo, self.notes_repo, self.dummy, self.config)
        app = create_app(config=self.config, service=self.service, study_service=mock.MagicMock())
        app.state.qa_notes = self.qa_notes
        self.http = TestClient(app)

    def tearDown(self) -> None:
        """Close DB session and remove temporary directories."""
        self.session_ctx.__exit__(None, None, None)
        self.tmpdir.cleanup()

    def test_http_qa_ask_summarize_save_mastery_and_push(self) -> None:
        """Verify end-to-end HTTP lifecycle for Q&A ask, summarize, save, mastery toggle, and source push."""
        ask_res = self.http.post(
            "/api/courses/BIO101/qa/ask", json={"question": "核心原理？", "lecture_no": 1}
        )
        self.assertEqual(ask_res.status_code, 200)
        cid = ask_res.json()["conversation_id"]

        sum_res = self.http.post(
            "/api/courses/BIO101/qa/summarize", json={"conversation_id": cid, "lecture_no": 1}
        )
        self.assertEqual(sum_res.status_code, 200)
        summary = sum_res.json()

        save_res = self.http.post(
            "/api/courses/BIO101/notes",
            json={
                "title": summary["title"],
                "content_markdown": summary["markdown"],
                "lecture_no": 1,
                "tags": summary["tags"],
            },
        )
        self.assertEqual(save_res.status_code, 200)
        note_id = save_res.json()["id"]

        listed = self.http.get("/api/courses/BIO101/notes?tag=L01")
        self.assertEqual(len(listed.json()["notes"]), 1)

        m_res = self.http.patch(f"/api/courses/BIO101/notes/{note_id}/mastery", json={"status": "mastered"})
        self.assertEqual(m_res.json()["mastery_status"], "mastered")

        push_res = self.http.post(f"/api/courses/BIO101/notes/{note_id}/push_to_source")
        self.assertTrue(push_res.json()["is_uploaded_as_source"])

        del_res = self.http.delete(f"/api/courses/BIO101/notes/{note_id}")
        self.assertEqual(del_res.status_code, 200)

    def test_mcp_qa_tools_and_confirm_guard(self) -> None:
        """Verify MCP QA tools including confirm=True guard for push_note_to_source."""
        mcp = build_mcp_server(
            service=self.service,
            study_service=mock.MagicMock(),
            config=self.config,
            qa_notes=self.qa_notes,
        )
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        ans = json.loads(asyncio.run(tools["ask_notebook_question"].fn("BIO101", "什麼是細胞膜？", 1)))
        self.assertIn("深入解析", ans["answer"])

        saved = json.loads(tools["save_qa_note"].fn("BIO101", "細胞膜", "# 細胞膜\n\n雙層磷脂。", 1))
        note_id = saved["id"]

        notes = json.loads(tools["list_course_notes"].fn("BIO101", "L01"))
        self.assertEqual(len(notes["notes"]), 1)

        denied = json.loads(asyncio.run(tools["push_note_to_source"].fn("BIO101", note_id)))
        self.assertFalse(denied["confirmed"])

        approved = json.loads(asyncio.run(tools["push_note_to_source"].fn("BIO101", note_id, confirm=True)))
        self.assertTrue(approved["confirmed"])
        self.assertTrue(approved["is_uploaded_as_source"])

    def test_qa_ask_with_web_search_supplements_references(self) -> None:
        """When use_web_search=True, QANotesService attaches supplemental web_references."""

        async def _fake_web_search(query: str) -> list[dict[str, str]]:
            return [{"title": f"Web: {query}", "url": "https://example.com", "snippet": "Supplemental"}]

        self.qa_notes.web_search_fn = _fake_web_search
        off_res = self.http.post(
            "/api/courses/BIO101/qa/ask",
            json={"question": "細胞膜組成", "lecture_no": 1, "use_web_search": False},
        )
        self.assertEqual(off_res.status_code, 200)
        self.assertEqual(off_res.json()["web_references"], [])

        on_res = self.http.post(
            "/api/courses/BIO101/qa/ask",
            json={"question": "細胞膜組成", "lecture_no": 1, "use_web_search": True},
        )
        self.assertEqual(on_res.status_code, 200)
        web_refs = on_res.json()["web_references"]
        self.assertEqual(len(web_refs), 1)
        self.assertEqual(web_refs[0]["url"], "https://example.com")


if __name__ == "__main__":
    unittest.main()

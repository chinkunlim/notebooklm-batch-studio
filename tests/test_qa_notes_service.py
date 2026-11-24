"""Unit and integration tests for QANotesService (SPEC-011)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.notes_repository import QANoteRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course, Lecture
from notebooklm_batch_studio.services.qa_notes_service import QANotesService
from tests.dummy_client import DummyStudioClient


class TestQANotesService(unittest.IsolatedAsyncioTestCase):
    """Verify Q&A asking, formatted summarization, Markdown saving, tags, and source bundling."""

    def setUp(self) -> None:
        """Set up in-memory SQLite, temporary DATA_DIR, course BIO101, and QANotesService."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.folder = self.tmp / "BIO101"
        self.folder.mkdir()
        (self.folder / "Ch01-intro.pdf").write_bytes(b"%PDF-1.4 intro")
        (self.folder / "Ch02-cell.pdf").write_bytes(b"%PDF-1.4 cell")

        self.config = AppConfig(
            data_dir=self.tmp / "data", notebooklm_home=self.tmp / "cfg", log_to_file=False
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
                    ),
                    Lecture(
                        no=2,
                        topic="cell",
                        filename="Ch02-cell.pdf",
                        sha256="2",
                        source_id="src-2",
                        upload_status="ready",
                    ),
                ],
            )
        )
        self.service = QANotesService(self.course_repo, self.notes_repo, self.dummy, self.config)

    def tearDown(self) -> None:
        """Clean up DB session and temporary files."""
        self.session_ctx.__exit__(None, None, None)
        self.tmpdir.cleanup()

    async def test_ask_and_summarize_conversation(self) -> None:
        """Verify scoped asking and formatted Markdown summarization in same conversation."""
        res = await self.service.ask("BIO101", "什麼是滲透壓？", lecture_no=2)
        self.assertIn("深入解析", res["answer"])
        cid = res["conversation_id"]
        self.assertIsNotNone(cid)

        summary = await self.service.summarize_and_format("BIO101", cid, lecture_no=2)
        self.assertIn("# 核心觀念總結", summary["markdown"])
        self.assertIn("課程/BIO101/L02", summary["tags"])
        self.assertIn("L02", summary["tags"])
        self.assertIn("掌握度/待加強", summary["tags"])

    async def test_save_note_writes_markdown_and_updates_mastery(self) -> None:
        """Verify Markdown file with YAML frontmatter and mastery status toggling."""
        note = self.service.save_note(
            "BIO101",
            title="細胞膜運輸",
            content_markdown="# 細胞膜運輸\n\n主動運輸需要 ATP。",
            lecture_no=2,
            tags=["主題/生物學/細胞膜"],
            source_scene="quiz_explain",
            personal_memo="老師強調常考",
        )
        notes_dir = self.config.scratch_kind_dir("notes") / "BIO101"
        md_files = list(notes_dir.glob("*.md"))
        self.assertEqual(len(md_files), 1)
        content = md_files[0].read_text(encoding="utf-8")
        self.assertIn("課程/BIO101/L02", content)
        self.assertIn("類型/測驗追問", content)
        self.assertIn("掌握度/待加強", content)
        self.assertIn("老師強調常考", content)

        updated = self.service.toggle_mastery(note["id"], "mastered")
        self.assertEqual(updated["mastery_status"], "mastered")
        self.assertIn("掌握度/已搞懂", updated["tags"])
        self.assertNotIn("掌握度/待加強", updated["tags"])
        updated_content = md_files[0].read_text(encoding="utf-8")
        self.assertIn("掌握度/已搞懂", updated_content)

    async def test_push_single_and_bundle_notes_to_source(self) -> None:
        """Verify single note push and multi-note bundling upload PDFs without altering course folder."""
        n1 = self.service.save_note(
            "BIO101", title="重點一", content_markdown="# 重點一\n\n內容 A", lecture_no=1
        )
        n2 = self.service.save_note(
            "BIO101", title="重點二", content_markdown="# 重點二\n\n內容 B", lecture_no=1
        )

        pushed = await self.service.push_note_to_source("BIO101", n1["id"])
        self.assertTrue(pushed["is_uploaded_as_source"])
        self.assertIsNotNone(pushed["uploaded_source_id"])

        bundled = await self.service.bundle_notes_to_source("BIO101", [n1["id"], n2["id"]], "L01 精華總整")
        self.assertIn("source_id", bundled)
        self.assertEqual(bundled["bundled_count"], 2)
        remote_sources: list[dict[str, Any]] = await self.dummy.list_sources("nb-1")
        self.assertGreaterEqual(len(remote_sources), 2)


if __name__ == "__main__":
    unittest.main()

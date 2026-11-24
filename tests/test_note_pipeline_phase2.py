"""Offline unit and API tests for Phase 2 Note Studio integration (Refs: ADR-012, TASK-027)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.notes.note_pipeline_service import NotePipelineService


class NotePipelinePhase2Tests(unittest.TestCase):
    """Verify Phase 2 chapter listing, PDF push-to-source, legacy import, and HTTP/MCP parity."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.cfg = AppConfig(
            app_env="test",
            log_to_file=False,
            data_dir=self.data_dir,
            database_url=f"sqlite:///{self.data_dir / 'app.db'}",
        )
        self.study_dir = self.data_dir / "study" / "115-1" / "心理學研究法"
        self.notes_dir = self.study_dir / "03 Notes" / "NoteStudio"
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        (self.notes_dir / "ch01_科學研究導論_學習筆記.md").write_text(
            "---\nchapter: 01\ntitle: 科學研究導論\n---\n\n# 導論\n- [核心] {{定義:信度}}\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_list_chapters_and_push_to_source(self) -> None:
        svc = NotePipelineService(self.cfg, study_dir_resolver=lambda _: self.study_dir)
        chapters = svc.list_chapters("PSY201")
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]["chapter_id"], "ch01")

        uploaded_calls: list[tuple[str, str]] = []

        def _fake_upload(nb_id: str, pdf_path: str) -> str:
            uploaded_calls.append((nb_id, pdf_path))
            self.assertTrue(Path(pdf_path).is_file())
            return "src-uploaded-99"

        res = svc.push_to_source("PSY201", "ch01", "nb-abc", _fake_upload)
        self.assertEqual(res["status"], "uploaded")
        self.assertEqual(res["source_id"], "src-uploaded-99")
        self.assertEqual(uploaded_calls[0][0], "nb-abc")

    def test_course_detail_lecture_fields_used_by_notes_form(self) -> None:
        """The notes form reads `no`, `topic` and `relative_path` from course detail (Refs: ISSUE-056)."""
        from notebooklm_batch_studio.domain.models import Lecture
        from notebooklm_batch_studio.services.job_views import lecture_to_dict

        lec = Lecture(
            no=3,
            topic="種族與階級",
            filename="Ch03.pdf",
            sha256="x",
            category="02 Handout",
            relative_path="02 Handout/Ch03.pdf",
        )
        data = lecture_to_dict(lec)
        self.assertEqual(data["no"], 3)
        self.assertEqual(data["topic"], "種族與階級")
        self.assertEqual(data["relative_path"], "02 Handout/Ch03.pdf")
        js = (
            Path(__file__).resolve().parent.parent
            / "src/notebooklm_batch_studio/entrypoints/static/studio-notes-gen.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("l.lecture_no", js)
        self.assertNotIn("lec.lecture_no", js)

    def test_import_legacy_notes_skips_and_overwrites(self) -> None:
        legacy_dir = Path(self.tmp.name) / "legacy_notes"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "ch01_科學研究導論_學習筆記.md").write_text("NEW", encoding="utf-8")
        (legacy_dir / "ch02_研究倫理_學習筆記.md").write_text("CH02", encoding="utf-8")

        svc = NotePipelineService(self.cfg, study_dir_resolver=lambda _: self.study_dir)
        first = svc.import_legacy(legacy_dir, "PSY201", overwrite=False)
        self.assertEqual(first["copied"], ["ch02_研究倫理_學習筆記.md"])
        self.assertEqual(first["skipped"], ["ch01_科學研究導論_學習筆記.md"])

        second = svc.import_legacy(legacy_dir, "PSY201", overwrite=True)
        self.assertEqual(len(second["copied"]), 2)
        self.assertEqual(
            (self.notes_dir / "ch01_科學研究導論_學習筆記.md").read_text(encoding="utf-8"),
            "NEW",
        )

    def test_http_and_mcp_phase2_endpoints(self) -> None:
        app = create_app(config=self.cfg)
        app.state.note_pipeline_service = NotePipelineService(
            self.cfg, study_dir_resolver=lambda _: self.study_dir
        )
        app.state.note_upload_fn = lambda nb, pdf: f"src:{nb}:{Path(pdf).name}"
        client = TestClient(app, base_url="http://127.0.0.1:8768")

        res = client.get("/api/notes/chapters/PSY201")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["chapters"][0]["chapter_id"], "ch01")

        push_res = client.post(
            "/api/notes/push_to_source",
            json={"course_key": "PSY201", "chapter_id": "ch01", "notebook_id": "nb-1"},
        )
        self.assertEqual(push_res.status_code, 200)
        self.assertIn("src:nb-1:", push_res.json()["source_id"])

        mcp = build_mcp_server(config=self.cfg)
        tool_names = set(mcp._tool_manager._tools.keys())
        self.assertIn("notes_list_chapters", tool_names)
        self.assertIn("notes_push_to_source", tool_names)
        self.assertIn("notes_import_legacy", tool_names)

        confirm_msg = json.loads(
            mcp._tool_manager._tools["notes_push_to_source"].fn("PSY201", "ch01", "nb-1", False)
        )
        self.assertIn("confirm", confirm_msg)

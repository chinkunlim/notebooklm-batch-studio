"""Offline unit and API tests for Phase 1 Note Studio integration (Refs: ADR-012)."""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.note_pipeline import NoteBackend
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.notes.chapter_normalizer import normalize_step_markdown
from notebooklm_batch_studio.services.notes.module_prompts import (
    StepPromptContext,
    load_module_prompt,
)
from notebooklm_batch_studio.services.notes.note_pipeline_service import (
    ChapterNoteRequest,
    NotePipelineService,
)
from notebooklm_batch_studio.services.notes.step_validator import validate_step_output


class _FakeGeminiWebDriver:
    """Offline stub mimicking GeminiWebDriver for 7-step note generation."""

    def __init__(self) -> None:
        self.prompts_received: list[str] = []
        self.uploaded: list[Path] = []
        self.model: str = ""
        self.chat_title: str = ""

    def open_chapter_chat(self, title: str = "") -> None:
        self.chat_title = title

    def set_model(self, model_name: str) -> None:
        self.model = model_name

    def upload_files(self, paths: list[Path]) -> None:
        self.uploaded.extend(paths)

    def rename_chat(self, title: str) -> bool:
        self.chat_title = title
        return True

    def send_prompt_and_read(self, prompt: str, **kwargs: Any) -> str:
        del kwargs
        self.prompts_received.append(prompt)
        if "模組一" in prompt:
            return "# 模組一\n```flowchart\nA --> B\n```\n<!-- END -->"
        if "模組三" in prompt:
            return "# 模組三\n:::QEC\nQ: Why?\nE: Evidence [cite: 12]\nC: Claim\n:::\n<!-- END -->"
        if "模組五" in prompt:
            return "# 模組五\n| A | B |\n|---|---|\n| 1 | 2 |\n<!-- END -->"
        return (
            "- [核心] {{定義:操作型定義}} 是指可測量的指標 "
            '<u style="text-decoration: underline wavy #dc2626">必考</u>。\n'
            "<!-- END -->"
        )


class NotePipelinePhase1Tests(unittest.TestCase):
    """Verify Phase 1 prompt loading, dual-backend generation, stitching, and HTTP/MCP parity."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.cfg = AppConfig(
            app_env="test",
            log_to_file=False,
            data_dir=self.data_dir,
            database_url=f"sqlite:///{self.data_dir / 'app.db'}",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_standalone_prompt_loading_and_override(self) -> None:
        ctx = StepPromptContext("心理學研究法", "ch01", "科學研究導論")
        prompt = load_module_prompt("01_mindmap", ctx)
        self.assertIn("心理學研究法", prompt)
        self.assertIn("ch01 科學研究導論", prompt)
        self.assertIn("<!-- END -->", prompt)

        override_dir = self.data_dir / "prompts" / "modular_specs"
        override_dir.mkdir(parents=True, exist_ok=True)
        (override_dir / "01_mindmap_spec.md").write_text(
            "# Custom\n## Gemini 提示詞\n````text\n"
            "自訂 {{COURSE_NAME}} {{CHAPTER_ID}} {{CHAPTER_TITLE}}\n````\n",
            encoding="utf-8",
        )
        overridden = load_module_prompt("01_mindmap", ctx, override_dir=override_dir)
        self.assertIn("自訂 心理學研究法 ch01 科學研究導論", overridden)

    def test_normalizer_and_validator_preserve_semantic_tags(self) -> None:
        raw = (
            "```markdown\n- [核心] {{定義:信度}} [cite: 10, 11] "
            '<u style="text-decoration: underline wavy #dc2626">重點</u>\n```\n<!-- END -->'
        )
        res = validate_step_output(raw)
        self.assertTrue(res.is_valid)
        cleaned = normalize_step_markdown(res.clean_markdown)
        self.assertIn("[核心]", cleaned)
        self.assertIn("{{定義:信度}}", cleaned)
        self.assertIn("{{重要:重點}}", cleaned)
        self.assertIn("(p. 10, 11)", cleaned)

        refusal = validate_step_output("我只是一个语言模型，不能理解或回复你的这个问题。")
        self.assertFalse(refusal.is_valid)

    def test_gemini_web_primary_generates_and_stitches_md_with_version_archive(self) -> None:
        fake_driver = _FakeGeminiWebDriver()

        @contextmanager
        def _factory(req: ChapterNoteRequest) -> Generator[_FakeGeminiWebDriver, None, None]:
            del req
            yield fake_driver

        study_dir = self.data_dir / "study" / "115-1" / "心理學研究法"
        svc = NotePipelineService(self.cfg, driver_factory=_factory)
        pdf = Path(self.tmp.name) / "ch01.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        req = ChapterNoteRequest(
            course_key="PSY201",
            course_name="心理學研究法",
            chapter_id="ch01",
            chapter_title="科學研究導論",
            pdf_path=pdf,
            backend=NoteBackend.GEMINI_WEB,
            study_dir=study_dir,
        )
        out = svc.run_chapter(req)
        self.assertEqual(out["status"], "done")
        self.assertEqual(len(out["completed_steps"]), 7)
        stitched = Path(out["stitched_path"])
        self.assertTrue(stitched.is_file())
        self.assertEqual(stitched.parent, study_dir / "03 Notes" / "NoteStudio")
        content = stitched.read_text(encoding="utf-8")
        self.assertIn("chapter: 01", content)
        self.assertIn("title: 科學研究導論", content)
        self.assertIn(":::QEC", content)
        self.assertIn("{{重要:必考}}", content)

        # Rerun archives previous stitched output inside 03 Notes/NoteStudio/versions/
        svc.run_chapter(req)
        versions_dir = study_dir / "03 Notes" / "NoteStudio" / "versions" / "ch01"
        self.assertTrue(any(versions_dir.iterdir()))

    def test_notebooklm_fallback_backend_uses_source_ids(self) -> None:
        mock_client = MagicMock()
        mock_client.ask_in_conversation = AsyncMock(
            side_effect=[
                ("# 模組一\n```flowchart\nA --> B\n```\n<!-- END -->", "conv-1"),
                ("# 模組二\n- [核心] {{定義:效度}}\n<!-- END -->", "conv-1"),
                ("# 模組三\n:::QEC\nQ: q\nE: e\nC: c\n:::\n<!-- END -->", "conv-1"),
                ("# 模組四\n筆記\n<!-- END -->", "conv-1"),
                ("# 模組五\n| A | B |\n|---|---|\n| 1 | 2 |\n<!-- END -->", "conv-1"),
                ("# 模組六\n白話\n<!-- END -->", "conv-1"),
                ("# 模組七\n題目\n<!-- END -->", "conv-1"),
            ]
        )
        from notebooklm_batch_studio.adapters.notebooklm.note_driver import NotebookLMNoteDriver

        @contextmanager
        def _nb_factory(req: ChapterNoteRequest) -> Generator[NotebookLMNoteDriver, None, None]:
            yield NotebookLMNoteDriver(mock_client, req.notebook_id, req.source_ids)

        svc = NotePipelineService(self.cfg, driver_factory=_nb_factory)
        req = ChapterNoteRequest(
            course_key="PSY201",
            course_name="心理學研究法",
            chapter_id="ch01",
            chapter_title="科學研究導論",
            backend=NoteBackend.NOTEBOOKLM,
            notebook_id="nb-123",
            source_ids=["src-01"],
        )
        out = svc.run_chapter(req)
        self.assertEqual(out["status"], "done")
        self.assertEqual(out["backend"], "notebooklm")
        self.assertEqual(mock_client.ask_in_conversation.await_count, 7)

    def test_http_and_mcp_routes_registered(self) -> None:
        app = create_app(config=self.cfg)
        client = TestClient(app, base_url="http://127.0.0.1:8768")
        res = client.get("/api/notes/prompts")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["prompts"]), 7)

        prev = client.post(
            "/api/notes/prompts/preview",
            json={
                "step_id": "01_mindmap",
                "course_name": "心理學研究法",
                "chapter_id": "ch01",
                "chapter_title": "科學研究導論",
            },
        )
        self.assertEqual(prev.status_code, 200)
        self.assertIn("心理學研究法", prev.json()["prompt"])

        mcp = build_mcp_server(config=self.cfg)
        tool_names = set(mcp._tool_manager._tools.keys())
        self.assertIn("notes_list_prompts", tool_names)
        self.assertIn("notes_preview_prompt", tool_names)
        self.assertIn("notes_generate_chapter", tool_names)
        out_json = json.loads(mcp._tool_manager._tools["notes_list_prompts"].fn())
        self.assertEqual(len(out_json["prompts"]), 7)

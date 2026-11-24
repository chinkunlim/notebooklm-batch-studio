"""Behavior tests for the note-studio pipeline as rewritten in this project (SPEC-013, TASK-029).

note-studio's own tests target its `pipeline_coordinator` / `batch_orchestrator`, which were not
ported. These tests carry over the scenarios that still apply (model matching, refusal detection,
step validation, pause persistence, soft-fail, quota wait, single-module rerun) and run them
against `NotePipelineService`, `validate_step_output`, and `NoteStateManager`.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.gemini.web_driver import GeminiQuotaExceededError
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.note_pipeline import (
    GeminiRefusalError,
    ModelMismatchError,
    QuotaExceededError,
    is_gemini_refusal,
    is_model_match,
)
from notebooklm_batch_studio.services.notes.note_pipeline_service import (
    ChapterNoteRequest,
    NotePipelineService,
)
from notebooklm_batch_studio.services.notes.state_manager import NoteStateManager
from notebooklm_batch_studio.services.notes.step_validator import validate_step_output

# Refusals Gemini actually sent (copied from note-studio tests/test_gemini_refusal.py).
REAL_REFUSALS = [
    "请恕我爱莫能助，我只是一个语言模型，不能理解或回复你的这个问题。",
    "我是一个文本 AI，这超出了我的能力范围。",
    "由于程序代码的局限，我没法办到。",
    "I'm just a language model, so I can't help you with that.",
]

GOOD_REPLIES = {
    "模組一": "# 模組一\n```flowchart\nA --> B\n```\n<!-- END -->",
    "模組三": "# 模組三\n:::QEC\nQ: q\nE: e\nC: c\n:::\n<!-- END -->",
    "模組五": "# 模組五\n| A | B |\n|---|---|\n| 1 | 2 |\n<!-- END -->",
}
DEFAULT_REPLY = "- [核心] {{定義:信度}} 內容。\n<!-- END -->"


class _ScriptedDriver:
    """Driver stub whose reply per module can be overridden or made to raise."""

    def __init__(self, overrides: dict[str, Any] | None = None) -> None:
        self.overrides = overrides or {}
        self.prompts: list[str] = []

    def open_chapter_chat(self, title: str = "") -> None:
        del title

    def set_model(self, model_name: str) -> None:
        del model_name

    def upload_files(self, paths: list[Path]) -> None:
        del paths

    def rename_chat(self, title: str) -> bool:
        del title
        return True

    def send_prompt_and_read(self, prompt: str, **kwargs: Any) -> str:
        del kwargs
        self.prompts.append(prompt)
        for marker, reply in self.overrides.items():
            if marker in prompt:
                if isinstance(reply, Exception):
                    raise reply
                return str(reply)
        for marker, reply in GOOD_REPLIES.items():
            if marker in prompt:
                return reply
        return DEFAULT_REPLY


class DomainHelpersTest(unittest.TestCase):
    """Model matching and refusal detection (cases from note-studio)."""

    def test_model_match_table(self) -> None:
        self.assertTrue(is_model_match("4 Argon", "Used 4 Argon"))
        self.assertTrue(is_model_match("4 Argon", "使用了 4 Argon"))
        self.assertFalse(is_model_match("4 Argon", "Used 3.5 Flash-Lite"))
        self.assertFalse(is_model_match("4 Argon", "unknown"))
        self.assertFalse(is_model_match("3.1 Pro", "Argon"))
        self.assertTrue(is_model_match("3.1 Pro", "Used 3.1 Pro"))

    def test_refusals_detected_but_long_notes_are_not(self) -> None:
        for text in REAL_REFUSALS:
            self.assertTrue(is_gemini_refusal(text), text)
        note = "# 模組一：心智圖\n" + "生涯諮商理論說明。" * 200 + "\n研究者以語言模型分析訪談逐字稿。"
        self.assertFalse(is_gemini_refusal(note))

    def test_refusal_and_model_mismatch_pause_like_quota(self) -> None:
        self.assertTrue(issubclass(GeminiRefusalError, QuotaExceededError))
        self.assertTrue(issubclass(ModelMismatchError, QuotaExceededError))


class StepValidatorTest(unittest.TestCase):
    """`validate_step_output` rules."""

    def test_empty_refusal_missing_end_and_tokens(self) -> None:
        self.assertFalse(validate_step_output("   ").is_valid)
        self.assertFalse(validate_step_output(REAL_REFUSALS[0]).is_valid)
        truncated = validate_step_output("# 模組三\n內容")
        self.assertFalse(truncated.is_valid)
        self.assertTrue(any("END" in e for e in truncated.errors))
        missing = validate_step_output("# 模組三\n內容\n<!-- END -->", required_tokens=(":::QEC",))
        self.assertIn("缺少必要結構標記：:::QEC", missing.errors)

    def test_unbalanced_math_and_clean_output(self) -> None:
        self.assertFalse(validate_step_output("$$ x^2\n<!-- END -->").is_valid)
        ok = validate_step_output("$$ x $$ ```\n$$\n```\n<!-- END -->")
        self.assertTrue(ok.is_valid, ok.errors)
        self.assertNotIn("<!-- END -->", ok.clean_markdown)


class StateManagerTest(unittest.TestCase):
    """Per-course JSON state and cross-process pause files."""

    def test_state_roundtrip_pause_across_instances_and_safe_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            first = NoteStateManager(root)
            first.update_chapter_state("PSY 201/x", "ch01", {"status": "done"})
            first.request_pause("PSY 201/x")
            second = NoteStateManager(root)  # a different process sees the same files
            self.assertTrue(second.is_pause_requested("PSY 201/x"))
            self.assertEqual(second.load_course_state("PSY 201/x")["chapters"]["ch01"]["status"], "done")
            second.clear_pause("PSY 201/x")
            self.assertFalse(first.is_pause_requested("PSY 201/x"))
            files = [p for p in root.rglob("*") if p.is_file()]
            self.assertTrue(all(p.resolve().is_relative_to(root.resolve()) for p in files))
            self.assertFalse(any(p.suffix == ".tmp" for p in files))


class PipelineBehaviorTest(unittest.TestCase):
    """`NotePipelineService.run_chapter` outcomes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        data_dir = Path(self.tmp.name) / "data"
        self.cfg = AppConfig(app_env="test", log_to_file=False, data_dir=data_dir)
        self.study_dir = data_dir / "study" / "115-1" / "心理學"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _service(self, driver: _ScriptedDriver) -> NotePipelineService:
        @contextmanager
        def _factory(req: ChapterNoteRequest) -> Generator[_ScriptedDriver, None, None]:
            del req
            yield driver

        return NotePipelineService(self.cfg, driver_factory=_factory)

    def _request(self, **kw: Any) -> ChapterNoteRequest:
        base: dict[str, Any] = {
            "course_key": "PSY201",
            "course_name": "心理學",
            "chapter_id": "ch01",
            "chapter_title": "導論",
            "study_dir": self.study_dir,
        }
        base.update(kw)
        return ChapterNoteRequest(**base)

    def _modules(self) -> Path:
        return (self.study_dir / "03 Notes" / "NoteStudio" / "modules" / "ch01").resolve()

    def test_soft_fail_matrix_step_does_not_abort(self) -> None:
        driver = _ScriptedDriver({"模組五": "沒有表格\n<!-- END -->"})
        out = self._service(driver).run_chapter(self._request())
        self.assertEqual(out["status"], "done")
        self.assertIn("05_matrix", out["completed_steps"])
        self.assertFalse((self._modules() / "05_matrix.md").exists())

    def test_hard_failure_marks_chapter_failed(self) -> None:
        driver = _ScriptedDriver({"模組三": "缺少 QEC\n<!-- END -->"})
        svc = self._service(driver)
        with self.assertRaises(RuntimeError):
            svc.run_chapter(self._request())
        chapter = svc.get_status("PSY201")["chapters"]["ch01"]
        self.assertEqual(chapter["status"], "failed")
        self.assertIn("03_qec", chapter["last_error"])

    def test_quota_error_records_quota_wait(self) -> None:
        driver = _ScriptedDriver({"模組二": QuotaExceededError("limit reached")})
        svc = self._service(driver)
        out = svc.run_chapter(self._request())
        self.assertEqual(out["status"], "quota_wait")
        self.assertEqual(svc.get_status("PSY201")["chapters"]["ch01"]["status"], "quota_wait")

    def test_real_gemini_quota_error_from_web_driver_is_quota_wait(self) -> None:
        resume = datetime.now(timezone.utc) + timedelta(hours=1)
        error = GeminiQuotaExceededError("額度已用完", raw_text="額度已用完", resume_after=resume)
        svc = self._service(_ScriptedDriver({"模組四": error}))
        out = svc.run_chapter(self._request())
        self.assertEqual(out["status"], "quota_wait")
        self.assertTrue((self._modules() / "03_qec.md").exists())

    def test_pause_request_stops_before_next_step(self) -> None:
        svc = self._service(_ScriptedDriver())
        original = svc.state.update_chapter_state

        def _pause_after_first(course_key: str, chapter_id: str, patch: dict[str, Any]) -> None:
            original(course_key, chapter_id, patch)
            if patch.get("completed_steps") == ["01_mindmap"]:
                svc.state.request_pause(course_key)

        svc.state.update_chapter_state = _pause_after_first  # type: ignore[method-assign]
        out = svc.run_chapter(self._request())
        self.assertEqual(out["status"], "paused")
        self.assertTrue((self._modules() / "01_mindmap.md").exists())
        self.assertFalse((self._modules() / "02_outline.md").exists())

    def test_single_module_rerun_keeps_other_modules_and_archives(self) -> None:
        svc = self._service(_ScriptedDriver())
        svc.run_chapter(self._request())
        first_outline = (self._modules() / "02_outline.md").read_text(encoding="utf-8")
        rerun_driver = _ScriptedDriver({"模組三": "# 模組三 新版\n:::QEC\nQ\n:::\n<!-- END -->"})
        out = self._service(rerun_driver).run_chapter(self._request(steps_override=["03_qec"]))
        self.assertEqual(out["completed_steps"], ["03_qec"])
        self.assertEqual(len(rerun_driver.prompts), 1)
        self.assertIn("新版", (self._modules() / "03_qec.md").read_text(encoding="utf-8"))
        self.assertEqual((self._modules() / "02_outline.md").read_text(encoding="utf-8"), first_outline)
        archived = list((self._modules().parent.parent / "versions" / "ch01").rglob("03_qec.md"))
        self.assertEqual(len(archived), 1)
        stitched = Path(out["stitched_path"]).read_text(encoding="utf-8")
        self.assertIn(":::QEC\nQ\n:::", stitched)  # composer drops each module's own heading line

    def test_state_file_is_json_under_data_dir(self) -> None:
        svc = self._service(_ScriptedDriver())
        svc.run_chapter(self._request())
        state_files = list((self.cfg.state_dir / "notes").glob("*.json"))
        self.assertEqual(len(state_files), 1)
        self.assertEqual(
            json.loads(state_files[0].read_text(encoding="utf-8"))["chapters"]["ch01"]["status"], "done"
        )


if __name__ == "__main__":
    unittest.main()

"""Offline dummy Gemini Notebook client and payload builders for chaos & E2E simulation tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from notebooklm_batch_studio.domain.repositories import NotebookLMClientProtocol


def build_quiz_payload(count: int = 55) -> dict[str, Any]:
    """Build a valid multi-question quiz payload matching Gemini Notebook schema.

    Args:
        count: Number of unique questions to generate.

    Returns:
        Dictionary suitable for parsing by `parse_notebooklm_quiz`.
    """
    questions = [
        {
            "question": f"Ch01 模擬試題 {idx}: 何者正確？",
            "answerOptions": [
                {"text": f"正確選項 {idx}", "isCorrect": True, "rationale": "符合原理"},
                {"text": f"幹擾選項A {idx}", "isCorrect": False, "rationale": "概念混淆"},
                {"text": f"幹擾選項B {idx}", "isCorrect": False, "rationale": "條件不足"},
            ],
            "hint": "思考基礎定義",
        }
        for idx in range(1, count + 1)
    ]
    return {"title": "Dummy Quiz", "questions": questions}


def build_flashcards_payload() -> dict[str, Any]:
    """Build a valid flashcards payload matching Gemini Notebook schema.

    Returns:
        Dictionary suitable for parsing by `parse_notebooklm_flashcards`.
    """
    return {
        "title": "Dummy Flashcards",
        "cards": [
            {
                "front": {"flashcardContentBlock": [{"type": "text", "content": "主動運輸"}]},
                "back": {"flashcardContentBlock": [{"type": "text", "content": "需消耗 ATP"}]},
            },
            {
                "front": {"flashcardContentBlock": [{"type": "text", "content": "滲透作用"}]},
                "back": {"flashcardContentBlock": [{"type": "text", "content": "水分子穿過半透膜"}]},
            },
        ],
    }


def build_mindmap_payload() -> dict[str, Any]:
    """Build a valid hierarchical mind map tree payload.

    Returns:
        Dictionary suitable for parsing by `parse_notebooklm_mindmap`.
    """
    return {
        "name": "細胞生物學總覽",
        "children": [
            {"name": "細胞膜", "children": [{"name": "磷脂雙層"}]},
            {"name": "能量代謝", "children": [{"name": "ATP 合成"}]},
        ],
    }


class DummyStudioClient(NotebookLMClientProtocol):
    """Offline dummy client covering all 12 artifact types and interactive learning aids."""

    def __init__(self) -> None:
        """Initialize call log and sequence counter."""
        self.calls: list[str] = []
        self._seq = 0

    def _next_id(self, prefix: str) -> str:
        """Generate a unique synthetic identifier.

        Args:
            prefix: Type label prefix.

        Returns:
            Unique artifact or notebook identifier.
        """
        self._seq += 1
        return f"{prefix}-{self._seq}"

    def check_auth(self) -> bool:
        """Return authenticated status.

        Returns:
            Always True in dummy mode.
        """
        return True

    async def quota_retry_after(self) -> int | None:
        """Return no quota cooldown in dummy mode.

        Returns:
            None.
        """
        return None

    async def get_quota_status(self) -> dict[str, Any]:
        """Return unavailable quota summary so dummy runs skip live throttling.

        Returns:
            Dictionary with available=False.
        """
        return {"available": False}

    async def get_source_limit(self) -> int | None:
        """Return generous dummy notebook source cap.

        Returns:
            50.
        """
        return 50

    async def find_notebook_by_title(self, title: str) -> str | None:
        """Return None so each new course creates a distinct dummy notebook.

        Args:
            title: Notebook title.

        Returns:
            None.
        """
        return None

    async def list_ready_sources(self, notebook_id: str) -> dict[str, str]:
        """Return empty source mapping for fresh dummy notebooks.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            Empty dict.
        """
        return {}

    async def create_notebook(self, title: str) -> str:
        """Record notebook creation and return a dummy id.

        Args:
            title: Notebook title.

        Returns:
            Dummy notebook identifier.
        """
        self.calls.append(f"create_notebook:{title}")
        return self._next_id("nb")

    async def upload_source(self, notebook_id: str, file_path: str) -> str:
        """Record PDF upload and return a source id.

        Args:
            notebook_id: Notebook identifier.
            file_path: Local PDF path.

        Returns:
            Dummy source identifier.
        """
        self.calls.append(f"upload:{Path(file_path).name}")
        return f"src-{Path(file_path).stem}"

    async def wait_source_ready(self, notebook_id: str, source_id: str, timeout_seconds: int = 180) -> None:
        """Complete immediately for dummy source indexing.

        Args:
            notebook_id: Notebook identifier.
            source_id: Uploaded source identifier.
            timeout_seconds: Unused wait limit.
        """
        return

    async def ask(self, notebook_id: str, question: str, source_ids: list[str] | None = None) -> str:
        """Answer key-point extraction or question explanation requests cleanly.

        Args:
            notebook_id: Notebook identifier.
            question: Prompt text.
            source_ids: Optional source filters.

        Returns:
            JSON key points if requested, otherwise Markdown explanation.
        """
        if "JSON" in question or "重點" in question:
            return json.dumps(
                [
                    {
                        "quote": "Cell membranes regulate selective transport",
                        "page": 1,
                        "importance": 3,
                        "note": "核心重點",
                    }
                ]
            )
        return "核心重點在於細胞膜具備選擇通透性，依濃度梯度或 ATP 進行運輸。"

    async def ask_in_conversation(
        self, notebook_id: str, question: str, source_ids: list[str] | None, conversation_id: str | None
    ) -> tuple[str, str | None]:
        """Continue or start a dummy AI tutor conversation.

        Args:
            notebook_id: Notebook identifier.
            question: Student question.
            source_ids: Optional source filters.
            conversation_id: Existing conversation identifier.

        Returns:
            Tuple of (reply, conversation_id).
        """
        cid = conversation_id or self._next_id("conv")
        return f"針對「{question}」的引導提示：先回顧細胞膜結構。", cid

    async def generate_audio(self, notebook_id: str, source_ids: list[str], **_: Any) -> str:
        """Generate dummy audio id."""
        return self._next_id("aud")

    async def download_audio(self, notebook_id: str, output_path: str, **_: Any) -> None:
        """Write dummy M4A bytes."""
        Path(output_path).write_bytes(b"ftypM4A dummy-audio")

    async def generate_quiz(self, notebook_id: str, source_ids: list[str], **_: Any) -> str:
        """Generate dummy quiz id."""
        return self._next_id("quiz")

    async def download_quiz(self, notebook_id: str, output_path: str, **_: Any) -> None:
        """Write valid 55-question dummy quiz JSON."""
        Path(output_path).write_text(json.dumps(build_quiz_payload(55), ensure_ascii=False), encoding="utf-8")

    async def generate_flashcards(self, notebook_id: str, source_ids: list[str], **_: Any) -> str:
        """Generate dummy flashcards id."""
        return self._next_id("fc")

    async def download_flashcards(self, notebook_id: str, output_path: str, **_: Any) -> None:
        """Write valid dummy flashcards JSON."""
        Path(output_path).write_text(
            json.dumps(build_flashcards_payload(), ensure_ascii=False), encoding="utf-8"
        )

    async def generate_mind_map(self, notebook_id: str, source_ids: list[str], **_: Any) -> str:
        """Generate dummy mind map note id."""
        return self._next_id("mm")

    async def download_mind_map(self, notebook_id: str, output_path: str, **_: Any) -> None:
        """Write valid dummy mind map JSON."""
        Path(output_path).write_text(
            json.dumps(build_mindmap_payload(), ensure_ascii=False), encoding="utf-8"
        )

    async def generate_report(self, notebook_id: str, source_ids: list[str], **_: Any) -> str:
        """Generate dummy report id."""
        return self._next_id("rep")

    async def download_report(self, notebook_id: str, output_path: str, **_: Any) -> None:
        """Write Markdown report content."""
        Path(output_path).write_text("# 細胞生物學重點報告\n\n- 磷脂雙層構成膜結構。\n", encoding="utf-8")

    async def generate_slide_deck(self, notebook_id: str, source_ids: list[str], **_: Any) -> str:
        """Generate dummy slide deck id."""
        return self._next_id("slide")

    async def download_slide_deck(self, notebook_id: str, output_path: str, **_: Any) -> None:
        """Write dummy slide deck bytes."""
        Path(output_path).write_bytes(b"%PDF-1.4 dummy-slides")

    async def generate_infographic(self, notebook_id: str, source_ids: list[str], **_: Any) -> str:
        """Generate dummy infographic id."""
        return self._next_id("info")

    async def download_infographic(self, notebook_id: str, output_path: str, **_: Any) -> None:
        """Write a valid PNG image for PIL device export verification."""
        Image.new("RGB", (1200, 800), (31, 77, 58)).save(output_path, "PNG")

    async def generate_data_table(self, notebook_id: str, source_ids: list[str], **_: Any) -> str:
        """Generate dummy data table id."""
        return self._next_id("tbl")

    async def download_data_table(self, notebook_id: str, output_path: str, **_: Any) -> None:
        """Write dummy CSV table."""
        Path(output_path).write_text("概念,機制,消耗能量\n擴散,順濃度梯度,否\n", encoding="utf-8")

    async def generate_video(self, notebook_id: str, source_ids: list[str], **_: Any) -> str:
        """Generate dummy video id."""
        return self._next_id("vid")

    async def download_video(self, notebook_id: str, output_path: str, **_: Any) -> None:
        """Write dummy MP4 video bytes."""
        Path(output_path).write_bytes(b"ftypmp42 dummy-video")

    async def rename_artifact(self, notebook_id: str, artifact_id: str, title: str) -> None:
        """Record artifact rename call."""
        self.calls.append(f"rename_artifact:{artifact_id}:{title}")

    async def rename_mind_map(self, notebook_id: str, note_id: str, title: str) -> None:
        """Record mind map rename call."""
        self.calls.append(f"rename_mind_map:{note_id}:{title}")

    async def list_artifacts(self, notebook_id: str) -> list[dict[str, Any]]:
        """Return empty remote artifact list for sync calls."""
        return []

    async def find_latest_artifact(self, notebook_id: str, artifact_type: str | None = None) -> str | None:
        """Return dummy artifact id fallback."""
        return "art-latest-1"

    async def download_artifact_by_kind(self, *args: Any, **kwargs: Any) -> str:
        """Download dummy artifact payload to path."""
        out_path = str(args[3] if len(args) > 3 else kwargs.get("output_path", ""))
        Path(out_path).write_text("{}", encoding="utf-8")
        return out_path

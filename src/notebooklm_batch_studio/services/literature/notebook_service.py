"""Gemini Notebook integration for literature search and Western-academic Literature Reviews."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.exceptions import QuotaExceededError
from notebooklm_batch_studio.domain.literature.tracker import TrackedItem
from notebooklm_batch_studio.domain.notebooklm_protocol import NotebookLMClientProtocol
from notebooklm_batch_studio.services.literature.manager import LiteratureManager
from notebooklm_batch_studio.services.preferences_service import PreferencesService

logger = logging.getLogger(__name__)

LITERATURE_NOTEBOOK_TITLE = "Literature Library (文獻總庫)"
PREF_KEY_NOTEBOOK_ID = "literature.notebook_id"

WESTERN_REVIEW_PROMPT = """請嚴格根據這份指定的論文來源，撰寫一篇符合西方重點大學
（如 Oxford / Harvard / Stanford 研究所標準）的精簡單篇 Literature Review
（以繁體中文撰寫，關鍵學術專有名詞請保留英文原文於括號內），並使用以下七段 Markdown 結構：

## 1. Bibliographic Citation (APA 7th)
- {apa}

## 2. Research Purpose & Central Thesis
- 說明本文欲解決的核心研究問題（Research Question）與中心論點（Central Thesis）。

## 3. Theoretical Framework & Key Constructs
- 摘述本文所依據的理論架構、核心構念（Constructs）與操作型定義。

## 4. Methodology & Analytical Design
- 簡述研究設計、樣本特徵（Sample / N）、測量工具或資料分析方法。

## 5. Key Findings & Empirical Evidence
- 條列最關鍵的實證發現與支持數據／論證。

## 6. Critical Evaluation (Strengths, Limitations & Gaps)
- 以西方學術批判視角評估本研究之方法論優勢、內外在效度限制與尚未解決的研究缺口（Research Gaps）。

## 7. Synthesis & Future Research Implications
- 說明本文對所屬領域的理論貢獻、實務意涵，以及可延伸的未來研究方向。
"""


class LiteratureNotebookService:
    """Manages the dedicated Gemini Notebook for literature Q&A and Literature Reviews."""

    def __init__(
        self,
        notebooklm: NotebookLMClientProtocol,
        manager: LiteratureManager,
        prefs: PreferencesService,
    ) -> None:
        """Initialize the service with NotebookLM client, literature manager, and preferences.

        Args:
            notebooklm: Gemini Notebook client adapter.
            manager: LiteratureManager bound to active session.
            prefs: PreferencesService storing `literature.notebook_id`.
        """
        self.notebooklm = notebooklm
        self.manager = manager
        self.prefs = prefs

    def get_status(self) -> dict[str, Any]:
        """Return current Gemini Literature Notebook status and sync/review counts.

        Returns:
            Dictionary with `notebook_id`, `notebook_url`, `total_with_pdf`, `synced_count`, `reviewed_count`.
        """
        nb_id = self.prefs.get_all().get(PREF_KEY_NOTEBOOK_ID, "")
        items = self.manager.lit_repo.list_items()
        with_pdf = [i for i in items if i.file]
        synced = [i for i in with_pdf if i.source_id]
        reviewed = [i for i in items if i.review_markdown]
        return {
            "notebook_id": nb_id or None,
            "notebook_url": f"https://notebook.google.com/notebook/{nb_id}" if nb_id else None,
            "total_with_pdf": len(with_pdf),
            "synced_count": len(synced),
            "reviewed_count": len(reviewed),
        }

    async def ensure_notebook(self) -> str:
        """Return existing Literature Library Gemini Notebook ID, or create one automatically.

        Returns:
            Gemini Notebook ID string.
        """
        saved_id = self.prefs.get_all().get(PREF_KEY_NOTEBOOK_ID, "").strip()
        if saved_id:
            return saved_id
        existing = await self.notebooklm.find_notebook_by_title(LITERATURE_NOTEBOOK_TITLE)
        nb_id = existing or await self.notebooklm.create_notebook(LITERATURE_NOTEBOOK_TITLE)
        self.prefs.update({PREF_KEY_NOTEBOOK_ID: nb_id})
        logger.info("Configured Literature Gemini Notebook: %s", nb_id)
        return nb_id

    async def _sync_one_item(
        self, nb_id: str, item: TrackedItem, ready_sources: dict[str, str]
    ) -> TrackedItem:
        """Upload one literature PDF to `nb_id` (or reuse matching ready source).

        Args:
            nb_id: Target Gemini Notebook ID.
            item: Literature item with a local PDF.
            ready_sources: Map of remote source filename -> source_id.

        Returns:
            Updated `TrackedItem` carrying `source_id`.
        """
        if item.source_id:
            return item
        if item.file and item.file in ready_sources:
            updated = replace(item, source_id=ready_sources[item.file])
            self.manager.lit_repo.upsert_item(updated)
            return updated
        pdf_path = self.manager.resolve_pdf_path(item.key)
        if pdf_path is None or not pdf_path.is_file():
            return item
        src_id = await self.notebooklm.upload_source(nb_id, str(pdf_path))
        await self.notebooklm.wait_source_ready(nb_id, src_id)
        updated = replace(item, source_id=src_id)
        self.manager.lit_repo.upsert_item(updated)
        return updated

    async def sync_pdfs(self, keys: list[str] | None = None) -> dict[str, Any]:
        """Ensure Literature Notebook exists and upload any un-synced downloaded PDFs.

        Args:
            keys: Optional subset of item keys to sync; None syncs all PDFs.

        Returns:
            Dictionary with `notebook_id`, `uploaded`, and `total_synced`.
        """
        nb_id = await self.ensure_notebook()
        ready = await self.notebooklm.list_ready_sources(nb_id)
        items = self.manager.lit_repo.list_items()
        if keys is not None:
            wanted = set(keys)
            items = [i for i in items if i.key in wanted]

        uploaded = 0
        for item in items:
            if not item.file or item.source_id:
                continue
            updated = await self._sync_one_item(nb_id, item, ready)
            if updated.source_id:
                uploaded += 1
        return {**self.get_status(), "uploaded": uploaded}

    async def query(self, question: str) -> dict[str, Any]:
        """Ask Gemini Notebook across all uploaded literature to find relevant papers.

        Args:
            question: Natural language search or synthesis question.

        Returns:
            Dictionary with `notebook_id`, `answer`, and `references`.
        """
        nb_id = await self.ensure_notebook()
        res = await self.notebooklm.ask_qa(nb_id, question)
        return {"notebook_id": nb_id, **res}

    def _save_review_file(self, item: TrackedItem, markdown: str) -> Path:
        """Write `<key>_Literature_Review.md` into the `reviews/` subfolder next to the PDF.

        Args:
            item: Reviewed literature item.
            markdown: Generated Markdown review text.

        Returns:
            Path to the written `.md` file.
        """
        reviews_dir = self.manager.resolve_target_dir(item) / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        out_path = reviews_dir / f"{item.key}_Literature_Review.md"
        out_path.write_text(markdown, encoding="utf-8")
        return out_path

    async def generate_review(self, key: str, force: bool = False) -> TrackedItem:
        """Generate a Western-academic Literature Review for one paper via Gemini Notebook.

        Args:
            key: Literature item key.
            force: Regenerate even if `review_markdown` already exists.

        Returns:
            Updated `TrackedItem` with `review_markdown` populated.

        Raises:
            ValueError: When the item or its PDF does not exist.
        """
        item = self.manager.lit_repo.get_item(key)
        if item is None:
            raise ValueError(f"Literature item not found: {key}")
        if item.review_markdown and not force:
            return item
        if not item.file:
            raise ValueError("PDF has not been downloaded yet.")

        if not item.source_id:
            await self.sync_pdfs(keys=[key])
            item = self.manager.lit_repo.get_item(key) or item
        if not item.source_id:
            raise ValueError("Could not upload PDF to Gemini Notebook.")

        nb_id = await self.ensure_notebook()
        prompt = WESTERN_REVIEW_PROMPT.format(apa=item.apa or item.input)
        review_md = await self.notebooklm.ask(nb_id, prompt, source_ids=[item.source_id])
        self._save_review_file(item, review_md)
        updated = replace(item, review_markdown=review_md)
        self.manager.lit_repo.upsert_item(updated)
        logger.info("Generated Western Literature Review for %s", key)
        return updated

    async def generate_missing_reviews(
        self,
        quota_wait_seconds: float = 300.0,
        progress_cb: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Generate Literature Reviews for all downloaded items, waiting and resuming on quota limits.

        Args:
            quota_wait_seconds: Seconds to wait when Gemini quota is exhausted before retrying.
            progress_cb: Optional status callback receiving human-readable progress text.

        Returns:
            Summary dictionary with `generated` and `errors` lists.
        """
        await self.sync_pdfs()
        pending = [i for i in self.manager.lit_repo.list_items() if i.file and not i.review_markdown]
        generated: list[str] = []
        errors: list[dict[str, str]] = []
        idx = 0
        while idx < len(pending):
            item = pending[idx]
            if progress_cb:
                progress_cb(f"生成 Literature Review ({idx + 1}/{len(pending)})：{item.key}")
            try:
                await self.generate_review(item.key)
                generated.append(item.key)
                idx += 1
            except QuotaExceededError as exc:
                logger.warning(
                    "Gemini quota exhausted during %s; waiting %.0fs: %s", item.key, quota_wait_seconds, exc
                )
                if progress_cb:
                    progress_cb(f"額度已達上限，等待恢復後自動繼續 ({idx}/{len(pending)})…")
                await asyncio.sleep(quota_wait_seconds)
            except Exception as exc:
                if "quota" in str(exc).lower() or "429" in str(exc):
                    logger.warning(
                        "Rate/quota limit during %s; waiting %.0fs: %s", item.key, quota_wait_seconds, exc
                    )
                    if progress_cb:
                        progress_cb(f"額度暫時受限，等待恢復後自動繼續 ({idx}/{len(pending)})…")
                    await asyncio.sleep(quota_wait_seconds)
                    continue
                logger.warning("Failed review for %s: %s", item.key, exc)
                errors.append({"key": item.key, "error": str(exc)})
                idx += 1
        return {"generated": generated, "errors": errors, **self.get_status()}

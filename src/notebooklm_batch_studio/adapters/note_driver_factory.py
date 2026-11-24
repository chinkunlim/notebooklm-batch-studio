"""Driver factory binding Gemini Web and NotebookLM adapters for note generation."""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from typing import Any, Callable, Generator

from notebooklm_batch_studio.adapters.gemini.auth_runtime import ChromeGeminiLoginRuntime
from notebooklm_batch_studio.adapters.gemini.browser_session import (
    BrowserSessionManager,
    DriverOptions,
)
from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.adapters.notebooklm.note_driver import NotebookLMNoteDriver
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.note_pipeline import DriverUnavailableError, NoteBackend
from notebooklm_batch_studio.services.notes.gemini_auth_service import GeminiAuthService

logger = logging.getLogger(__name__)


def build_note_driver_factory(cfg: AppConfig) -> Callable[[Any], Any]:
    """Create a context-manager factory selecting `gemini_web` or `notebooklm`.

    Args:
        cfg: Application configuration.

    Returns:
        Callable accepting a `ChapterNoteRequest`-like object and yielding a driver.
    """

    @contextmanager
    def _factory(request: Any) -> Generator[Any, None, None]:
        """Yield an initialized driver for the requested backend.

        Args:
            request: ChapterNoteRequest specifying backend, model, and notebook IDs.

        Yields:
            Active driver instance.
        """
        if request.backend == NoteBackend.NOTEBOOKLM:
            if not request.notebook_id:
                raise DriverUnavailableError("使用 Gemini Notebook 備用後端時必須提供 notebook_id。")
            adapter = NotebookLMAdapter(config=cfg)
            yield NotebookLMNoteDriver(adapter, request.notebook_id, request.source_ids)
            return

        mgr = BrowserSessionManager(config=cfg)
        opts = DriverOptions(headless=False, model=request.model, auto_close=False)
        with mgr.open_driver(options=opts) as drv:
            yield drv

    return _factory


def build_note_upload_fn(cfg: AppConfig) -> Callable[[str, str], str]:
    """Create a synchronous callback uploading a PDF source to Gemini Notebook.

    Args:
        cfg: Application configuration.

    Returns:
        Callable `(notebook_id, pdf_path) -> source_id`.
    """

    def _upload(notebook_id: str, pdf_path: str) -> str:
        """Upload `pdf_path` to `notebook_id` via `NotebookLMAdapter`.

        Args:
            notebook_id: Target Gemini Notebook ID.
            pdf_path: Local PDF file path.

        Returns:
            Remote source ID.
        """
        adapter = NotebookLMAdapter(config=cfg)
        return str(asyncio.run(adapter.upload_source(notebook_id, pdf_path)))

    return _upload


def build_gemini_auth_service(cfg: AppConfig) -> GeminiAuthService:
    """Create `GeminiAuthService` wired with the real-Chrome login runtime (Refs: ISSUE-053).

    Args:
        cfg: Application configuration.

    Returns:
        Configured `GeminiAuthService` instance.
    """
    profile_dir = cfg.gemini_profile_dir
    runtime = ChromeGeminiLoginRuntime(profile_dir=profile_dir, chrome_path=cfg.chrome_path)
    return GeminiAuthService(config=cfg, login_runtime=runtime)

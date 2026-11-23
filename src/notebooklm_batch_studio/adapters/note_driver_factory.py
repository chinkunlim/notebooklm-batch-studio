"""Driver factory binding Gemini Web and NotebookLM adapters for note generation."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Callable, Generator

from notebooklm_batch_studio.adapters.gemini.browser_session import (
    BrowserSessionManager,
    DriverOptions,
)
from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.adapters.notebooklm.note_driver import NotebookLMNoteDriver
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.note_pipeline import DriverUnavailableError, NoteBackend

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

        mgr = BrowserSessionManager(
            data_dir=cfg.data_dir,
            chrome_path=cfg.chrome_path,
            startup_timeout_seconds=cfg.playwright_startup_timeout_seconds,
        )
        opts = DriverOptions(headless=False, model=request.model, auto_close=False)
        with mgr.open_driver(options=opts) as drv:
            yield drv

    return _factory

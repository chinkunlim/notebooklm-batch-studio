"""Web server background work: the per-minute study pass and watching study/ like `watch` (SPEC-028/029).

New `02 Handouts` PDFs are registered and scheduled, new textbook chapters become lectures without
scheduling, whole books only get a hint — exactly the `watch` command's handlers (`cli_watch`).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.entrypoints.cli_watch import (
    _BatchEnv,
    _on_pdf_detected,
    _resolve_registered_study_dir,
)
from notebooklm_batch_studio.entrypoints.folder_sync import start_folder_sync
from notebooklm_batch_studio.services.watcher import CourseWatcher

logger = logging.getLogger(__name__)


def start_web_watcher(config: AppConfig, engine: Any) -> CourseWatcher | None:
    """Start watching study/ when `watch_in_web` is on.

    Args:
        config: Application configuration.
        engine: SQLAlchemy engine shared with the web server.

    Returns:
        The running watcher (call `stop()` on shutdown), or None when turned off.
    """
    if not config.watch_in_web:
        return None
    config.study_root_dir.mkdir(parents=True, exist_ok=True)
    env = _BatchEnv(engine, NotebookLMAdapter(config), config)
    watcher = CourseWatcher(
        config.study_root_dir,
        lambda course_dir, pdf: _on_pdf_detected(course_dir, pdf, env),
        resolve_course=lambda pdf: _resolve_registered_study_dir(pdf, env),
        layout=config.study_layout,
    )
    watcher.set_pause_check(lambda: config.consolidate_pause_path.exists())  # ADR-015
    watcher.start()
    logger.info("Web server is watching %s", config.study_root_dir)
    return watcher


def start_background(app: Any, cfg: AppConfig) -> Callable[[], None]:
    """Start the per-minute study pass and, with WATCH_IN_WEB, the study/ watcher (SPEC-028/029).

    Args:
        app: The FastAPI application (`app.state.session_factory`).
        cfg: Application configuration.

    Returns:
        Callable stopping both.
    """
    folder_sync = start_folder_sync(cfg, app.state.session_factory)
    watcher = start_web_watcher(cfg, app.state.session_factory.kw.get("bind"))

    def stop() -> None:
        """Stop the pass and the watcher."""
        folder_sync.stop()
        if watcher is not None:
            watcher.stop()

    return stop

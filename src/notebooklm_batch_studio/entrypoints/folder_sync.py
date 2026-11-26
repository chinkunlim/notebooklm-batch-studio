"""Start the background pass that fills in 01–05 for new subject folders under study/ (SPEC-028).

Used by the web server (lifespan) and by `watch`. The pass only creates missing category folders;
it never registers, schedules, moves or renames anything.
"""

from __future__ import annotations

import logging
from typing import Any

from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.services.new_course_folders import FolderSyncLoop, sync_new_study_folders

logger = logging.getLogger(__name__)


def start_folder_sync(config: AppConfig, session_factory: Any, interval: float = 60.0) -> FolderSyncLoop:
    """Run a folder pass now and every `interval` seconds in the background.

    Args:
        config: Application configuration.
        session_factory: Callable returning a SQLAlchemy session context manager.
        interval: Seconds between passes.

    Returns:
        The running loop (call `stop()` on shutdown).
    """

    def run_once() -> None:
        """One pass with its own database session."""
        with session_factory() as session:
            sync_new_study_folders(config, CourseRepository(session))

    loop = FolderSyncLoop(run_once, interval)
    loop.start()
    logger.info("Study folder sync started (every %.0fs)", interval)
    return loop

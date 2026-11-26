"""Background pass every 60 seconds (SPEC-028, SPEC-029), used by the web server and by `watch`.

Each pass: fill in 01–05 for new subject folders and registered courses; add PDFs dropped into
`scratch/literature/` or a course's `Literature_Review/` to the literature list; and send one macOS
notification per new course folder, whole textbook waiting to be split, or missing/changed lecture PDF.
Nothing here registers courses, schedules jobs, splits books, uploads, or calls Gemini or the network.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.literature.factory import AdapterLiteratureRuntime
from notebooklm_batch_studio.adapters.pdf_textbook import PypdfTextbookTools
from notebooklm_batch_studio.adapters.system_notify import send_notification
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import CourseStatus
from notebooklm_batch_studio.services.lecture_files import LectureFileChecker
from notebooklm_batch_studio.services.literature.manager import LiteratureManager
from notebooklm_batch_studio.services.new_course_folders import (
    FolderSyncLoop,
    find_new_course_folders,
    sync_new_study_folders,
)
from notebooklm_batch_studio.services.study_alerts import AlertNotifier, collect_alerts
from notebooklm_batch_studio.services.textbook_split import TextbookService

logger = logging.getLogger(__name__)

Sender = Callable[[str, str], object]


def _step(name: str, fn: Callable[[], Any]) -> None:
    """Run one step of the pass; a failure is logged and does not stop the other steps.

    Args:
        name: Step name for the log.
        fn: The step.
    """
    try:
        fn()
    except Exception:
        logger.exception("Background pass step failed: %s", name)


def _alerts(config: AppConfig, session: Any, checker: LectureFileChecker) -> list[tuple[str, str, str]]:
    """Collect the current alerts.

    Args:
        config: Application configuration.
        session: Database session.
        checker: Lecture file checker (keeps its hash cache between passes).

    Returns:
        `(key, title, message)` tuples.
    """
    repo = CourseRepository(session)
    courses = repo.list_courses()
    active = [c.code for c in courses if c.status != CourseStatus.ARCHIVED]
    books = TextbookService(config, repo, PypdfTextbookTools()).pending_textbooks(active)
    return collect_alerts(find_new_course_folders(config, repo), books, checker.issues(courses))


def build_pass(config: AppConfig, session_factory: Any, send: Sender) -> Callable[[], None]:
    """Build one background pass.

    Args:
        config: Application configuration (`notify_on_complete` turns notifications on).
        session_factory: Callable returning a SQLAlchemy session context manager.
        send: `(title, message)` notification sender.

    Returns:
        Zero-argument callable running the pass.
    """
    checker = LectureFileChecker()
    notifier = AlertNotifier(config.study_alerts_path, send)

    def run_once() -> None:
        """Run all steps with one database session."""
        with session_factory() as session:
            repo = CourseRepository(session)
            _step("folders", lambda: sync_new_study_folders(config, repo))
            manager = LiteratureManager(
                config, LiteratureRepository(session), repo, AdapterLiteratureRuntime(config)
            )
            _step("literature", manager.sync_untracked_pdfs)
            if config.notify_on_complete:
                _step("alerts", lambda: notifier.notify_new(_alerts(config, session, checker)))
            session.commit()

    return run_once


def start_folder_sync(config: AppConfig, session_factory: Any, interval: float = 60.0) -> FolderSyncLoop:
    """Run the background pass now and every `interval` seconds.

    Args:
        config: Application configuration.
        session_factory: Callable returning a SQLAlchemy session context manager.
        interval: Seconds between passes.

    Returns:
        The running loop (call `stop()` on shutdown).
    """
    loop = FolderSyncLoop(build_pass(config, session_factory, send_notification), interval)
    loop.start()
    logger.info("Background study pass started (every %.0fs)", interval)
    return loop

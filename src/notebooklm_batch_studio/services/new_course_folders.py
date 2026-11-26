"""Find subject folders the user created or pasted under `study/<term>/` and fill in 01–05 (SPEC-027/028).

Only folders of the current term or later count; older unregistered folders belong to the learning-record
page's record-only registration (SPEC-016). School-named folders carry their course number; any other
folder (e.g. 「專題製作」) is a subject that still needs one. Nothing is registered or scheduled here.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import CourseStatus
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol
from notebooklm_batch_studio.services.course_parser import _collect_unique_lectures
from notebooklm_batch_studio.services.study_library import StudyLibraryService, TermEntry

logger = logging.getLogger(__name__)


def _current_term(active_terms: list[str], scanned_terms: list[str]) -> str:
    """Pick the term from which folders count as new.

    Args:
        active_terms: Terms of registered courses that are not archived.
        scanned_terms: Term folders found under `study/`.

    Returns:
        The newest active term, else the newest scanned term, else ''.
    """
    pool = [t for t in active_terms if t] or scanned_terms
    return max(pool) if pool else ""


def _subject_rows(entry: TermEntry, root: Path, config: AppConfig) -> list[dict[str, Any]]:
    """Describe the unregistered subject folders of one term.

    Args:
        entry: Scanned term.
        root: Resolved `study/` folder.
        config: Application configuration (layout).

    Returns:
        Rows for school-named candidates and for other non-hidden folders (which need a course number).
    """
    rows = [
        {
            "term": entry.term,
            "folder": c.folder,
            "path": str(root / entry.term / c.folder),
            "code": c.code,
            "name": c.name,
            "course_no": c.course_no,
            "needs_course_no": False,
            "lecture_count": c.lecture_count,
        }
        for c in entry.courses
        if not c.registered
    ]
    folders = [root / entry.term / n for n in entry.others if not n.startswith(".")]
    rows += [_unnumbered_row(entry.term, f, config) for f in folders if f.is_dir()]
    return sorted(rows, key=lambda r: r["folder"])


def _unnumbered_row(term: str, folder: Path, config: AppConfig) -> dict[str, Any]:
    """Describe a subject folder without a course number (e.g. 「專題製作」); it is typed in the wizard.

    Args:
        term: Academic term.
        folder: Subject folder.
        config: Application configuration (layout).

    Returns:
        Row with `needs_course_no=True`.
    """
    count = len(_collect_unique_lectures(folder, layout=config.study_layout))
    return {
        "term": term,
        "folder": folder.name,
        "path": str(folder),
        "code": "",
        "name": folder.name,
        "course_no": "",
        "needs_course_no": True,
        "lecture_count": count,
    }


def find_new_course_folders(config: AppConfig, course_repo: CourseRepositoryProtocol) -> list[dict[str, Any]]:
    """List unregistered subject folders in the current term or later.

    Args:
        config: Application configuration (`study_root_dir`, layout).
        course_repo: Course repository.

    Returns:
        `[{term, folder, path, code, name, course_no, needs_course_no, lecture_count}]`, by term then folder.
    """
    terms = StudyLibraryService(config, course_repo).scan()
    active = [c.term for c in course_repo.list_courses() if c.status != CourseStatus.ARCHIVED]
    since = _current_term(active, [t.term for t in terms])
    root = config.study_root_dir.resolve()
    found = [row for entry in terms if entry.term >= since for row in _subject_rows(entry, root, config)]
    logger.info("New course folders since %s: %d", since or "(none)", len(found))
    return found


def sync_new_study_folders(config: AppConfig, course_repo: CourseRepositoryProtocol) -> list[dict[str, Any]]:
    """Find new subject folders and create their missing 01–05 folders (never moves or renames files).

    Args:
        config: Application configuration.
        course_repo: Course repository.

    Returns:
        The found subjects, each with `created`: category folders made in this pass.
    """
    found = find_new_course_folders(config, course_repo)
    layout = config.study_layout
    for row in found:
        folder = Path(row["path"])
        before = {p.name for p in folder.iterdir() if p.is_dir()}
        layout.ensure_tree(folder)
        row["created"] = sorted({p.name for p in folder.iterdir() if p.is_dir()} - before)
        if row["created"]:
            logger.info("Created %s in %s", ", ".join(row["created"]), folder)
    return found


class FolderSyncLoop:
    """Run a folder pass now and then every `interval` seconds in a daemon thread (SPEC-028)."""

    def __init__(self, run_once: Callable[[], Any], interval: float = 60.0) -> None:
        """Bind the pass and its interval.

        Args:
            run_once: One pass; exceptions are logged and the loop keeps going.
            interval: Seconds between passes.
        """
        self.run_once = run_once
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background thread (no-op when already running)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="study-folder-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Ask the thread to finish and wait briefly for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        """Run passes until stopped."""
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("Study folder sync pass failed")
            self._stop.wait(self.interval)

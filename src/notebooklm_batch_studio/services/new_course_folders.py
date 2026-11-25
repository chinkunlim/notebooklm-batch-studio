"""Suggest course folders the user created or pasted under `study/<term>/` but has not added (SPEC-027).

Only folders of the current term or later are suggested; older unregistered folders belong to the
learning-record page's record-only registration (SPEC-016). Nothing is registered or scheduled here.
"""

from __future__ import annotations

import logging
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import CourseStatus
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol
from notebooklm_batch_studio.services.study_library import StudyLibraryService

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


def find_new_course_folders(config: AppConfig, course_repo: CourseRepositoryProtocol) -> list[dict[str, Any]]:
    """List unregistered course folders in the current term or later.

    Args:
        config: Application configuration (`study_root_dir`, layout).
        course_repo: Course repository.

    Returns:
        `[{term, folder, path, code, name, lecture_count}]`, sorted by term then folder.
    """
    terms = StudyLibraryService(config, course_repo).scan()
    active = [c.term for c in course_repo.list_courses() if c.status != CourseStatus.ARCHIVED]
    since = _current_term(active, [t.term for t in terms])
    root = config.study_root_dir.resolve()
    found = [
        {
            "term": entry.term,
            "folder": cand.folder,
            "path": str(root / entry.term / cand.folder),
            "code": cand.code,
            "name": cand.name,
            "lecture_count": cand.lecture_count,
        }
        for entry in terms
        if entry.term >= since
        for cand in entry.courses
        if not cand.registered
    ]
    logger.info("New course folders since %s: %d", since or "(none)", len(found))
    return found

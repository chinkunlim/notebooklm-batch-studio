"""List existing subfolders of a course category so the web page can offer them as choices (path rule)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.domain.path_safety import ensure_within_roots, validate_path_segment

logger = logging.getLogger(__name__)


class CourseLookupProtocol(Protocol):
    """Course lookup capability."""

    def get_course(self, code: str) -> Course | None:
        """Return a course or None.

        Args:
            code: Course code.

        Returns:
            Course or None.
        """
        ...


def list_category_subfolders(repo: CourseLookupProtocol, code: str, category: str) -> list[str]:
    """Return visible subfolder names inside `<study_dir>/<category>/`.

    Args:
        repo: Course repository.
        code: Course code.
        category: Category folder name such as `01 Materials`.

    Returns:
        Sorted folder names; empty when the course has no study folder or the category is missing.

    Raises:
        CourseNotFoundError: Unknown course.
        PathSafetyError: `category` is not a single safe folder name.
    """
    course = repo.get_course(code)
    if course is None:
        raise CourseNotFoundError(f"找不到課程：{code}")
    validate_path_segment(category, "category")
    if not course.study_dir:
        return []
    root = Path(course.study_dir)
    base = ensure_within_roots(root / category, [root], "category")
    if not base.is_dir():
        return []
    return sorted(
        p.name for p in base.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")
    )

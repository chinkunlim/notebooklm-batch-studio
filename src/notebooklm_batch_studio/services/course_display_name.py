"""Change a course's display name without touching its code, subject, folder or notebook (SPEC-016)."""

from __future__ import annotations

import logging
from typing import Protocol

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError

logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 255


class CourseNameRepoProtocol(Protocol):
    """Repository capability needed to rename a course's display name."""

    def update_course_name(self, code: str, name: str) -> bool:
        """Persist a new display name.

        Args:
            code: Course code.
            name: Validated display name.

        Returns:
            True when the course exists and was updated.
        """
        ...


def normalize_display_name(name: str) -> str:
    """Trim and validate a course display name.

    Args:
        name: Raw name typed by the user.

    Returns:
        Trimmed name.

    Raises:
        ValueError: When the name is blank or longer than `MAX_NAME_LENGTH`.
    """
    clean = (name or "").strip()
    if not clean:
        raise ValueError("課程名稱不可空白")
    if len(clean) > MAX_NAME_LENGTH:
        raise ValueError(f"課程名稱最長 {MAX_NAME_LENGTH} 字")
    return clean


def set_course_display_name(repo: CourseNameRepoProtocol, code: str, name: str) -> dict[str, str]:
    """Validate and store a course's new display name.

    Args:
        repo: Repository implementing `update_course_name`.
        code: Course code.
        name: Raw new display name.

    Returns:
        `{"code": code, "name": clean_name}`.

    Raises:
        ValueError: When the name is invalid.
        CourseNotFoundError: When `code` is not registered.
    """
    clean = normalize_display_name(name)
    if not repo.update_course_name(code, clean):
        raise CourseNotFoundError(f"找不到課程：{code}")
    logger.info("Course display name changed: %s", code)
    return {"code": code, "name": clean}

"""Configurable study folder categories, semantic roles, and alias resolution (Refs: ADR-014).

Default category names use plural forms (`01 Materials`, `02 Handouts`, `03 Notes`, `04 Homework`,
`05 Assignments`), can be overridden via `STUDY_CATEGORIES`, and recognize legacy singular names
(`01 Material`, `02 Handout`) as aliases when reading without creating duplicate directories.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

_FORBIDDEN_SEGMENT_CHARS = ("/", "\\", "\x00", "*", "?", "[", "]")
_MAX_SEGMENT_LENGTH = 128


def _validate_category_segment(value: str) -> str:
    """Validate that a category name is a safe single path segment.

    Args:
        value: Raw category folder name.

    Returns:
        Validated segment string.

    Raises:
        ValueError: When empty, too long, hidden, or containing unsafe path characters.
    """
    if not value or len(value) > _MAX_SEGMENT_LENGTH:
        raise ValueError("study_category 長度不合法")
    if value.startswith(".") or any(ch in value for ch in _FORBIDDEN_SEGMENT_CHARS):
        raise ValueError(f"study_category 含有不允許的路徑字元：{value!r}")
    return value


class CategoryRole(str, Enum):
    """Semantic roles for the five top-level directories inside a course study folder."""

    MATERIALS = "materials"
    HANDOUTS = "handouts"
    NOTES = "notes"
    HOMEWORK = "homework"
    ASSIGNMENTS = "assignments"


_DEFAULT_NAMES: dict[CategoryRole, str] = {
    CategoryRole.MATERIALS: "01 Materials",
    CategoryRole.HANDOUTS: "02 Handouts",
    CategoryRole.NOTES: "03 Notes",
    CategoryRole.HOMEWORK: "04 Homework",
    CategoryRole.ASSIGNMENTS: "05 Assignments",
}

_DEFAULT_ALIASES: dict[CategoryRole, tuple[str, ...]] = {
    CategoryRole.MATERIALS: ("01 Material",),
    CategoryRole.HANDOUTS: ("02 Handout",),
    CategoryRole.NOTES: (),
    CategoryRole.HOMEWORK: (),
    CategoryRole.ASSIGNMENTS: (),
}


@dataclass(frozen=True)
class StudyLayout:
    """Mapping between semantic `CategoryRole` values and filesystem folder names/aliases.

    Attributes:
        names: Primary directory name for each of the five `CategoryRole` entries.
        aliases: Legacy or alternate directory names recognized when reading/scanning.
    """

    names: dict[CategoryRole, str]
    aliases: dict[CategoryRole, tuple[str, ...]]

    def all_names(self, role: CategoryRole) -> tuple[str, ...]:
        """Return `(primary_name, *aliases)` without duplicates for a role.

        Args:
            role: Target `CategoryRole`.

        Returns:
            Ordered tuple of folder names belonging to `role`.
        """
        primary = self.names[role]
        extras = tuple(a for a in self.aliases.get(role, ()) if a != primary)
        return (primary, *extras)

    def category_dirs(self, course_dir: Path, role: CategoryRole) -> list[Path]:
        """Return all existing directories on disk matching `role` (primary and aliases).

        Args:
            course_dir: Course study directory.
            role: Target `CategoryRole`.

        Returns:
            List of existing `Path` objects matching `role`.
        """
        return [course_dir / name for name in self.all_names(role) if (course_dir / name).is_dir()]

    def primary_dir(self, course_dir: Path, role: CategoryRole) -> Path:
        """Resolve the preferred directory path for `role` under `course_dir`.

        Uses the primary plural folder if it already exists or if no alias exists on disk; falls
        back to an existing alias directory so files are not split across duplicate folders.

        Args:
            course_dir: Course study directory.
            role: Target `CategoryRole`.

        Returns:
            Resolved category directory path.
        """
        primary = course_dir / self.names[role]
        if primary.is_dir():
            return primary
        for alias in self.aliases.get(role, ()):
            candidate = course_dir / alias
            if candidate.is_dir():
                return candidate
        return primary

    def ensure_tree(self, course_dir: Path) -> None:
        """Create missing category directories without duplicating existing aliases.

        Args:
            course_dir: Course study directory to initialize.
        """
        for role in CategoryRole:
            if not self.category_dirs(course_dir, role):
                (course_dir / self.names[role]).mkdir(parents=True, exist_ok=True)
        logger.debug("Ensured study layout directories under %s", course_dir)

    def role_of(self, name: str) -> CategoryRole | None:
        """Identify which `CategoryRole` corresponds to a folder name or alias.

        Args:
            name: Candidate directory name.

        Returns:
            Matching `CategoryRole`, or `None` when unrecognized.
        """
        clean = (name or "").strip()
        if not clean:
            return None
        for role in CategoryRole:
            if clean in self.all_names(role):
                return role
        return None

    def as_dict(self) -> dict[str, str]:
        """Serialize `{role.value: primary_name}` for HTTP/MCP responses.

        Returns:
            Dictionary mapping role identifier string to primary category folder name.
        """
        return {role.value: self.names[role] for role in CategoryRole}


DEFAULT_LAYOUT = StudyLayout(names=dict(_DEFAULT_NAMES), aliases=dict(_DEFAULT_ALIASES))


def layout_from_names(raw: str) -> StudyLayout:
    """Parse a comma-separated `STUDY_CATEGORIES` override into a `StudyLayout`.

    Args:
        raw: Comma-separated string containing exactly 5 category directory names in role order
            (`MATERIALS, HANDOUTS, NOTES, HOMEWORK, ASSIGNMENTS`).

    Returns:
        Configured `StudyLayout` preserving legacy singular read aliases.

    Raises:
        ValueError: When `raw` does not contain 5 valid single-segment directory names.
    """
    parts = [_validate_category_segment(part.strip()) for part in raw.split(",") if part.strip()]
    roles = list(CategoryRole)
    if len(parts) != len(roles):
        raise ValueError(f"STUDY_CATEGORIES must specify exactly {len(roles)} names, got {len(parts)}")
    if len(set(parts)) != len(parts):
        raise ValueError("STUDY_CATEGORIES names must be distinct")
    names = dict(zip(roles, parts, strict=True))
    aliases: dict[CategoryRole, tuple[str, ...]] = {}
    for role in roles:
        combined = (_DEFAULT_NAMES[role], *_DEFAULT_ALIASES[role])
        aliases[role] = tuple(item for item in combined if item != names[role])
    return StudyLayout(names=names, aliases=aliases)

"""Path-safety rules shared by every layer that builds file paths from outside input (Refs: ISSUE-045).

Identifiers such as course keys and chapter IDs end up as folder or file names, and
caller-supplied paths (study folders, chapter PDFs, legacy note folders) are read or
written. These helpers refuse anything that could escape the folders the app owns.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

# Characters that must never appear in a single path segment (separators, NUL, glob wildcards).
_FORBIDDEN_SEGMENT_CHARS = ("/", "\\", "\x00", "*", "?", "[", "]")
# Longest accepted identifier segment.
_MAX_SEGMENT_LENGTH = 128


class PathSafetyError(ValueError):
    """Raised when an identifier or path would leave the folders the app is allowed to use."""


def validate_path_segment(value: str, field_name: str) -> str:
    """Check that a value is safe to use as one folder or file-name segment.

    Args:
        value: Raw identifier such as a course key or chapter ID.
        field_name: Field name reported in the error message.

    Returns:
        The unchanged value when it is safe.

    Raises:
        PathSafetyError: Empty, too long, hidden (leading dot), or containing a separator / NUL.
    """
    if not value or len(value) > _MAX_SEGMENT_LENGTH:
        raise PathSafetyError(f"{field_name} 長度不合法")
    if value.startswith(".") or any(ch in value for ch in _FORBIDDEN_SEGMENT_CHARS):
        logger.warning("Rejected unsafe %s segment: %r", field_name, value)
        raise PathSafetyError(f"{field_name} 含有不允許的路徑字元：{value!r}")
    return value


def is_within(path: Path, root: Path) -> bool:
    """Tell whether `path` resolves to `root` itself or somewhere beneath it.

    Args:
        path: Candidate path (symlinks are resolved).
        root: Allowed root folder.

    Returns:
        True when the resolved path stays inside the resolved root.
    """
    return path.resolve().is_relative_to(root.resolve())


def ensure_within_roots(path: Path, roots: Iterable[Path | None], field_name: str) -> Path:
    """Resolve a caller-supplied path and require it to stay inside one of the allowed roots.

    Args:
        path: Caller-supplied path.
        roots: Allowed root folders; None entries are ignored.
        field_name: Field name reported in the error message.

    Returns:
        The resolved path.

    Raises:
        PathSafetyError: The path is outside every allowed root.
    """
    resolved = path.expanduser().resolve()
    for root in roots:
        if root is not None and resolved.is_relative_to(root.expanduser().resolve()):
            return resolved
    logger.warning("Rejected %s outside allowed roots: %s", field_name, resolved)
    raise PathSafetyError(f"{field_name} 不在允許的資料夾內：{resolved}")

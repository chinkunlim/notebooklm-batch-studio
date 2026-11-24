"""Course folder parsing and term-scoped course identity helpers (Refs: ADR-014, ISSUE-058).

Parses school-formatted course folders such as `CP__30000-團體諮商` or
`YY__5061AA-體育 (三)_超慢跑 AA` into canonical course numbers and names, and constructs
term-scoped course codes (`<term>_<course_no>`) validated against path traversal.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from notebooklm_batch_studio.domain.path_safety import PathSafetyError, validate_path_segment

logger = logging.getLogger(__name__)

#: Academic term folder format, e.g. `113-1`, `115-2`, `2026-1`.
TERM_PATTERN = re.compile(r"^\d{2,4}-\d{1,2}$")

#: School course folder format: `<dept>_{1,2}<num>-<title>`, e.g. `CP__30000-團體諮商`.
_COURSE_FOLDER_PATTERN = re.compile(r"^([A-Za-z]{1,6})_{1,2}([0-9A-Za-z]+)-(.+)$")


@dataclass(frozen=True)
class CourseFolderInfo:
    """Parsed metadata from a folder name inside a term directory.

    Attributes:
        course_no: Uppercase department+number identifier (e.g. `CP30000`), or `""` if not a course.
        name: Preserved course display title (or the stripped folder name when `is_course` is False).
        is_course: True when `folder_name` matches the school course naming convention.
    """

    course_no: str
    name: str
    is_course: bool


def parse_course_folder(folder_name: str) -> CourseFolderInfo:
    """Parse a folder basename into a `CourseFolderInfo` record.

    Args:
        folder_name: Basename of a directory under a semester/term folder.

    Returns:
        `CourseFolderInfo` with `is_course=True` for school-formatted names, otherwise `False`.
    """
    clean = (folder_name or "").strip()
    if not clean or clean.startswith("."):
        return CourseFolderInfo("", clean, False)
    match = _COURSE_FOLDER_PATTERN.match(clean)
    if not match:
        return CourseFolderInfo("", clean, False)
    course_no = f"{match.group(1)}{match.group(2)}".upper()
    title = match.group(3).strip()
    if not title:
        return CourseFolderInfo("", clean, False)
    return CourseFolderInfo(course_no=course_no, name=title, is_course=True)


def make_course_code(term: str, course_no: str) -> str:
    """Combine an academic term and course number into a path-safe course code.

    Args:
        term: Semester identifier matching `TERM_PATTERN` (e.g. `115-1`).
        course_no: Course number (e.g. `CP30000`).

    Returns:
        Canonical term-scoped course code such as `115-1_CP30000`.

    Raises:
        PathSafetyError: When `term` or `course_no` contains unsafe characters or is invalid.
    """
    clean_term = validate_path_segment((term or "").strip(), "term")
    if not TERM_PATTERN.match(clean_term):
        logger.warning("Rejected invalid academic term for course code: %r", clean_term)
        raise PathSafetyError(f"term 格式不合法：{clean_term!r}")
    clean_no = validate_path_segment((course_no or "").strip().upper(), "course_no")
    return validate_path_segment(f"{clean_term}_{clean_no}", "course_code")


def split_course_code(code: str) -> tuple[str, str]:
    """Split a course code into `(term, course_no)` when prefixed with a valid term.

    Args:
        code: Course code such as `115-1_CP30000` or legacy `BIO101`.

    Returns:
        `(term, course_no)` when a term prefix is present, otherwise `("", code)`.
    """
    clean = (code or "").strip()
    if "_" in clean:
        head, _, tail = clean.partition("_")
        if TERM_PATTERN.match(head) and tail:
            return head, tail
    return "", clean


def notebook_title(course_no: str, name: str, term: str) -> str:
    """Format the canonical Gemini Notebook title for a course.

    Args:
        course_no: Uppercase course number (e.g. `CP30000`).
        name: Course title (e.g. `團體諮商`).
        term: Academic term (e.g. `115-1`).

    Returns:
        Formatted notebook title, e.g. `"[CP30000] 團體諮商 (115-1)"`.
    """
    clean_no = (course_no or "").strip()
    clean_name = (name or "").strip()
    clean_term = (term or "").strip()
    if clean_no and clean_term:
        return f"[{clean_no}] {clean_name} ({clean_term})"
    if clean_no:
        return f"[{clean_no}] {clean_name}"
    return clean_name

"""Check that each lecture's PDF is still there and unchanged (SPEC-029).

Read-only: reports `missing` (file gone or renamed) and `changed` (same path, different SHA-256 than when
it was registered, so Gemini Notebook still holds the old version). Hashes are cached by size and
modification time so unchanged files are not re-read every minute.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.models import Course, CourseStatus
from notebooklm_batch_studio.services.course_parser import compute_pdf_sha256

logger = logging.getLogger(__name__)


class LectureFileChecker:
    """Find lecture PDFs that disappeared or changed; keeps a hash cache between calls."""

    def __init__(self, hasher: Callable[[Path], str] = compute_pdf_sha256) -> None:
        """Set the hash function.

        Args:
            hasher: Returns the SHA-256 hex digest of a file (tests count calls).
        """
        self.hasher = hasher
        self._cache: dict[str, tuple[int, int, str]] = {}

    def _sha(self, path: Path) -> str:
        """Hash a file, reusing the cached value while its size and modification time are unchanged.

        Args:
            path: Existing file.

        Returns:
            SHA-256 hex digest.
        """
        st = path.stat()
        cached = self._cache.get(str(path))
        if cached and cached[:2] == (st.st_size, st.st_mtime_ns):
            return cached[2]
        digest = self.hasher(path)
        self._cache[str(path)] = (st.st_size, st.st_mtime_ns, digest)
        return digest

    def issues(self, courses: list[Course]) -> list[dict[str, Any]]:
        """List missing or changed lecture PDFs of registered, not archived courses.

        Args:
            courses: Registered courses.

        Returns:
            `[{course_code, course_name, lecture_no, filename, relative_path, issue, sha256}]`.
        """
        found: list[dict[str, Any]] = []
        for course in courses:
            if course.status == CourseStatus.ARCHIVED or not course.study_dir:
                continue
            for lec in course.lectures:
                found += self._check(course, lec)
        if found:
            logger.info("Lecture file issues: %d", len(found))
        return found

    def _check(self, course: Course, lec: Any) -> list[dict[str, Any]]:
        """Check one lecture.

        Args:
            course: Its course.
            lec: Lecture entity.

        Returns:
            One issue row, or an empty list when the file is fine.
        """
        rel = lec.relative_path or lec.filename
        path = Path(course.study_dir) / rel
        row = {
            "course_code": course.code,
            "course_name": course.name,
            "lecture_no": lec.no,
            "filename": lec.filename,
            "relative_path": rel,
        }
        if not path.is_file():
            return [{**row, "issue": "missing", "sha256": ""}]
        digest = self._sha(path)
        if lec.sha256 and digest != lec.sha256:
            return [{**row, "issue": "changed", "sha256": digest}]
        return []

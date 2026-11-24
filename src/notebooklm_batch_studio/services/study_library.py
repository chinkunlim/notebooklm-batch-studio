"""Scan `DATA_DIR/study/` by academic term and register record-only courses without enqueueing jobs."""

from __future__ import annotations

import dataclasses
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.course_identity import (
    TERM_PATTERN,
    make_course_code,
    parse_course_folder,
)
from notebooklm_batch_studio.domain.models import Course, CourseStatus, ProfileName
from notebooklm_batch_studio.domain.path_safety import ensure_within_roots, validate_path_segment
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol
from notebooklm_batch_studio.services.course_parser import _collect_unique_lectures, scan_course_directory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CourseCandidate:
    """One course folder discovered inside `DATA_DIR/study/<term>/`.

    Attributes:
        term: Semester folder name (e.g. `115-1`).
        folder: Course folder basename (e.g. `CP__30000-團體諮商`).
        code: Canonical term-scoped course code (e.g. `115-1_CP30000`).
        name: Human-readable course name.
        lecture_count: Number of lecture PDFs found under `HANDOUTS`.
        registered: True when already persisted in the database.
        course_no: Normalized uppercase course number (e.g. `CP30000`).
    """

    term: str
    folder: str
    code: str
    name: str
    lecture_count: int
    registered: bool
    course_no: str = ""


@dataclass(frozen=True)
class TermEntry:
    """Scan summary for one academic term under `DATA_DIR/study/`.

    Attributes:
        term: Semester folder name (e.g. `115-1`).
        courses: Detected course folders in this term.
        others: Non-course folders and loose files in the term directory.
    """

    term: str
    courses: list[CourseCandidate]
    others: list[str]


class StudyLibraryService:
    """Discover term folders under `study_root_dir` and register courses without remote calls."""

    def __init__(self, config: AppConfig, course_repo: CourseRepositoryProtocol) -> None:
        """Initialize the study library scanner and registrar.

        Args:
            config: Application configuration providing `study_root_dir` and `study_layout`.
            course_repo: Persistence repository for courses.
        """
        self.config = config
        self.course_repo = course_repo

    def scan(self) -> list[TermEntry]:
        """Scan `DATA_DIR/study/` for academic term folders, course folders, and other entries.

        Returns:
            Sorted list of `TermEntry` summaries for valid semester directories.
        """
        root = self.config.study_root_dir
        if not root.is_dir():
            return []

        existing = self.course_repo.list_courses()
        by_code = {c.code: c for c in existing}
        by_dir = {str(Path(c.study_dir).resolve()): c for c in existing if c.study_dir}

        entries: list[TermEntry] = []
        for entry in sorted(root.iterdir(), key=lambda p: p.name):
            if entry.is_dir() and TERM_PATTERN.match(entry.name):
                entries.append(self._scan_term_dir(entry, (by_code, by_dir)))
        logger.info("Scanned study library: %d terms under %s", len(entries), root)
        return entries

    def _scan_term_dir(
        self, term_dir: Path, existing_maps: tuple[dict[str, Course], dict[str, Course]]
    ) -> TermEntry:
        """Scan one semester directory and classify course candidates vs other items.

        Args:
            term_dir: Path to `DATA_DIR/study/<term>`.
            existing_maps: Tuple of `(by_code, by_dir)` dictionaries for registered courses.

        Returns:
            Populated `TermEntry` with sorted candidates and non-course names.
        """
        by_code, by_dir = existing_maps
        term = term_dir.name
        courses: list[CourseCandidate] = []
        others: list[str] = []

        for child in sorted(term_dir.iterdir(), key=lambda p: p.name):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                candidate = self._inspect_subdir(term, child, by_code, by_dir)
                if candidate is not None:
                    courses.append(candidate)
                    continue
            others.append(child.name)
        return TermEntry(term=term, courses=courses, others=others)

    def _inspect_subdir(
        self, term: str, subdir: Path, by_code: dict[str, Course], by_dir: dict[str, Course]
    ) -> CourseCandidate | None:
        """Return a `CourseCandidate` if a subdirectory is a registered or school-named course.

        Args:
            term: Academic term string.
            subdir: Subdirectory inside `study/<term>/`.
            by_code: Registered courses keyed by code.
            by_dir: Registered courses keyed by resolved `study_dir`.

        Returns:
            `CourseCandidate` if recognized or already registered, else None.
        """
        resolved = str(subdir.resolve())
        existing = by_dir.get(resolved)
        layout = self.config.study_layout
        if existing is not None:
            count = len(_collect_unique_lectures(subdir, layout=layout))
            return CourseCandidate(
                term, subdir.name, existing.code, existing.name, count, True, existing.course_no
            )
        info = parse_course_folder(subdir.name)
        if not info.is_course:
            return None
        code = make_course_code(term, info.course_no)
        count = len(_collect_unique_lectures(subdir, layout=layout))
        return CourseCandidate(term, subdir.name, code, info.name, count, code in by_code, info.course_no)

    def _save_record_only(self, candidate: CourseCandidate, archive: bool) -> dict[str, Any]:
        """Persist one scanned study-library folder as a record-only course without jobs.

        Args:
            candidate: Scanned course candidate metadata.
            archive: Whether to set `status=CourseStatus.ARCHIVED` (default True).

        Returns:
            Summary dictionary for the registered course.
        """
        folder_dir = self.config.study_root_dir / candidate.term / candidate.folder
        ensure_within_roots(folder_dir, [self.config.study_root_dir], "course folder")
        scanned = scan_course_directory(
            folder_dir,
            custom_code=candidate.code,
            term=candidate.term,
            layout=self.config.study_layout,
        )
        course = dataclasses.replace(
            scanned,
            name=candidate.name,
            subject=candidate.name,
            term=candidate.term,
            course_no=candidate.course_no,
            study_dir=str(folder_dir.resolve()),
            profile=ProfileName.RECORD_ONLY,
            status=CourseStatus.ARCHIVED if archive else CourseStatus.ACTIVE,
            paused=False,
        )
        self.course_repo.save_course(course)
        logger.info("Registered study course %s (record-only, status=%s)", course.code, course.status.value)
        return {
            "code": course.code,
            "name": course.name,
            "term": course.term,
            "course_no": course.course_no,
            "profile": course.profile.value,
            "status": course.status.value,
            "lecture_count": len(course.lectures),
        }

    def register(self, codes: list[str], archive: bool = True) -> list[dict[str, Any]]:
        """Register discovered study-library courses by code without enqueueing generation jobs.

        Args:
            codes: Course codes to register (e.g. `['113-1_CP30000']`).
            archive: Whether to save registered courses with `status='archived'`.

        Returns:
            Per-code result dictionaries; already-registered codes return `skipped`.

        Raises:
            ValueError: When a requested code is not registered and not found in `study/`.
        """
        candidates = {c.code: c for t in self.scan() for c in t.courses}
        results: list[dict[str, Any]] = []
        for raw_code in codes:
            code = validate_path_segment(raw_code.strip(), "course_code")
            if self.course_repo.get_course(code) is not None:
                results.append({"code": code, "skipped": "already registered"})
                continue
            candidate = candidates.get(code)
            if candidate is None:
                raise ValueError(f"Study library course not found for code: {code}")
            results.append(self._save_record_only(candidate, archive=archive))
        return results

    def register_folder(self, term: str, folder: str, course_no: str) -> dict[str, Any]:
        """Manually register a non-standard folder under `study/<term>/` with an explicit course_no.

        Args:
            term: Academic term matching `TERM_PATTERN` (e.g. `115-1`).
            folder: Folder basename inside `DATA_DIR/study/<term>/` (e.g. `專題`).
            course_no: Alphanumeric course number assigned by the user (e.g. `PROJ1151`).

        Returns:
            Result dictionary for the newly registered or skipped course.

        Raises:
            FileNotFoundError: When `study/<term>/<folder>` does not exist.
        """
        clean_term = validate_path_segment(term.strip(), "term")
        clean_folder = validate_path_segment(folder.strip(), "folder")
        normalized_no = re.sub(r"[^A-Za-z0-9]", "", course_no).upper()
        code = make_course_code(clean_term, normalized_no)
        if self.course_repo.get_course(code) is not None:
            return {"code": code, "skipped": "already registered"}

        folder_dir = self.config.study_root_dir / clean_term / clean_folder
        ensure_within_roots(folder_dir, [self.config.study_root_dir], "study folder")
        if not folder_dir.is_dir():
            raise FileNotFoundError(f"Study folder not found: {folder_dir}")

        lecture_count = len(_collect_unique_lectures(folder_dir, layout=self.config.study_layout))
        candidate = CourseCandidate(
            term=clean_term,
            folder=clean_folder,
            code=code,
            name=clean_folder,
            lecture_count=lecture_count,
            registered=False,
            course_no=normalized_no,
        )
        return self._save_record_only(candidate, archive=True)

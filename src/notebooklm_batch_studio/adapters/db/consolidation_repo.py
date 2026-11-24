"""Database adapter for synchronizing paths during legacy data consolidation (Refs: SPEC-014, ADR-015)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.models import (
    ArtifactJobRecord,
    CourseRecord,
    LectureRecord,
    LiteratureItemRecord,
)
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.domain.models import Course, JobStatus

logger = logging.getLogger(__name__)


def _swap_path_prefix(value: str | None, prefixes: tuple[str, ...], new_dir: str) -> str | None:
    """Replace any matching directory prefix in `value` with `new_dir` (handling OS symlinks).

    Args:
        value: Stored filesystem path string or None.
        prefixes: Normalized source directory strings (raw and resolved).
        new_dir: Replacement directory string.

    Returns:
        Updated path string if a prefix matched, otherwise None.
    """
    if not value:
        return None
    for candidate in dict.fromkeys([value, os.path.realpath(value)]):
        for prefix in prefixes:
            if candidate == prefix:
                return new_dir
            if candidate.startswith(prefix + os.sep):
                return f"{new_dir}{candidate[len(prefix) :]}"
    return None


class ConsolidationRepository:
    """Reads courses and updates path/category columns inside a caller-managed DB transaction."""

    def __init__(self, session: Session) -> None:
        """Bind repository to an open SQLAlchemy session.

        Args:
            session: Active SQLAlchemy session.
        """
        self.session = session

    def list_courses(self) -> list[Course]:
        """Return all registered courses ordered by code.

        Returns:
            List of domain `Course` objects.
        """
        return CourseRepository(self.session).list_courses()

    def has_running_jobs(self) -> bool:
        """Return True when any artifact generation job is currently running.

        Returns:
            True if one or more `artifact_jobs` rows have status `running`.
        """
        running = (
            self.session.scalar(
                select(func.count())
                .select_from(ArtifactJobRecord)
                .where(ArtifactJobRecord.status == JobStatus.RUNNING.value)
            )
            or 0
        )
        return running > 0

    def rewrite_course_folder_paths(
        self,
        old_dir: str,
        new_dir: str,
        meta: dict[str, str] | None = None,
    ) -> dict[str, int]:
        """Update `courses` and `artifact_jobs` path fields referencing `old_dir` without committing.

        Args:
            old_dir: Previous course directory path.
            new_dir: Renamed course directory path.
            meta: Optional dictionary with `subject` / `course_no` overrides for matched courses.

        Returns:
            Dictionary of updated row counts per table (`courses`, `artifact_jobs`).
        """
        prefixes = tuple(dict.fromkeys([str(Path(old_dir)), str(Path(old_dir).resolve())]))
        meta_map = meta or {}
        course_hits = self._rewrite_courses(prefixes, new_dir, meta_map)
        job_hits = self._rewrite_jobs(prefixes, new_dir)
        self.session.flush()
        logger.info(
            "Rewrote folder paths (%s -> %s): courses=%d jobs=%d", old_dir, new_dir, course_hits, job_hits
        )
        return {"courses": course_hits, "artifact_jobs": job_hits}

    def _rewrite_courses(self, prefixes: tuple[str, ...], new_dir: str, meta: dict[str, str]) -> int:
        """Update `source_dir`, `study_dir`, and optional school metadata on matched `courses`.

        Args:
            prefixes: Matching old directory string variants.
            new_dir: Replacement directory string.
            meta: Optional `subject` / `course_no` overrides.

        Returns:
            Number of updated `CourseRecord` rows.
        """
        updated = 0
        for row in self.session.scalars(select(CourseRecord)).all():
            new_src = _swap_path_prefix(row.source_dir, prefixes, new_dir)
            new_study = _swap_path_prefix(row.study_dir, prefixes, new_dir)
            if new_src is None and new_study is None:
                continue
            if new_src is not None:
                row.source_dir = new_src
            if new_study is not None:
                row.study_dir = new_study
                if meta.get("subject"):
                    row.subject = meta["subject"]
                if meta.get("course_no") and not row.course_no:
                    row.course_no = meta["course_no"]
            updated += 1
        return updated

    def _rewrite_jobs(self, prefixes: tuple[str, ...], new_dir: str) -> int:
        """Update `output_file` and `interactive_path` on matched `artifact_jobs`.

        Args:
            prefixes: Matching old directory string variants.
            new_dir: Replacement directory string.

        Returns:
            Number of updated `ArtifactJobRecord` rows.
        """
        updated = 0
        for job in self.session.scalars(select(ArtifactJobRecord)).all():
            new_out = _swap_path_prefix(job.output_file, prefixes, new_dir)
            new_inter = _swap_path_prefix(job.interactive_path, prefixes, new_dir)
            if new_out is None and new_inter is None:
                continue
            if new_out is not None:
                job.output_file = new_out
            if new_inter is not None:
                job.interactive_path = new_inter
            updated += 1
        return updated

    def rewrite_category_name(
        self,
        old_category: str,
        new_category: str,
        course_code: str | None = None,
    ) -> dict[str, int]:
        """Update `lectures` and `literature_items` from a legacy singular category to plural.

        Args:
            old_category: Legacy singular category directory name.
            new_category: Primary plural category directory name.
            course_code: Optional course filter.

        Returns:
            Dictionary of updated counts (`lectures`, `literature_items`).
        """
        lec_stmt = select(LectureRecord).where(LectureRecord.category == old_category)
        lit_stmt = select(LiteratureItemRecord).where(LiteratureItemRecord.target_category == old_category)
        if course_code:
            lec_stmt = lec_stmt.where(LectureRecord.course_code == course_code)
            lit_stmt = lit_stmt.where(LiteratureItemRecord.course_code == course_code)
        lec_hits = 0
        for lec in self.session.scalars(lec_stmt).all():
            lec.category = new_category
            if lec.relative_path.startswith(f"{old_category}/"):
                lec.relative_path = f"{new_category}/{lec.relative_path[len(old_category) + 1 :]}"
            lec_hits += 1
        lit_hits = 0
        for lit in self.session.scalars(lit_stmt).all():
            lit.target_category = new_category
            lit_hits += 1
        self.session.flush()
        return {"lectures": lec_hits, "literature_items": lit_hits}

    def update_lecture_relative_path(self, course_code: str, old_rel: str, new_rel: str) -> int:
        """Update exact `relative_path` (and `filename`) when a colliding lecture PDF is suffixed.

        Args:
            course_code: Course code owning the lecture row.
            old_rel: Previous relative path inside the course directory.
            new_rel: Actual destination relative path after suffixing.

        Returns:
            Number of updated rows.
        """
        stmt = select(LectureRecord).where(
            LectureRecord.course_code == course_code, LectureRecord.relative_path == old_rel
        )
        hits = 0
        for lec in self.session.scalars(stmt).all():
            lec.relative_path = new_rel
            lec.filename = Path(new_rel).name
            lec.category = Path(new_rel).parts[0] if len(Path(new_rel).parts) > 1 else lec.category
            hits += 1
        if hits:
            self.session.flush()
        return hits

    def commit(self) -> None:
        """Commit the current consolidation database transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Roll back pending consolidation database changes."""
        self.session.rollback()

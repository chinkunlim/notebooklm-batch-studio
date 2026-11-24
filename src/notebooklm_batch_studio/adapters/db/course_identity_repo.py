"""Transactional database course-code identity repository (Refs: SPEC-014, ADR-014)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.models import (
    ArtifactJobRecord,
    CourseQANoteRecord,
    CourseRecord,
    ExplanationRecord,
    KeyPointsRecord,
    LectureRecord,
    LiteratureItemRecord,
    QuizAttemptRecord,
    QuizMistakeRecord,
    ReviewItemRecord,
    StudyProgressRecord,
    TutorMessageRecord,
    UiPreferenceRecord,
)
from notebooklm_batch_studio.domain.course_identity import split_course_code
from notebooklm_batch_studio.domain.models import JobStatus

logger = logging.getLogger(__name__)

_DIRECT_COURSE_TABLES: tuple[type[Any], ...] = (
    LectureRecord,
    ArtifactJobRecord,
    QuizAttemptRecord,
    QuizMistakeRecord,
    StudyProgressRecord,
    TutorMessageRecord,
    CourseQANoteRecord,
    LiteratureItemRecord,
)
_COMPOSITE_COURSE_TABLES: tuple[type[Any], ...] = (
    ReviewItemRecord,
    ExplanationRecord,
    KeyPointsRecord,
)


class CourseIdentityRepository:
    """Safely preview and rename a course primary key across all 11 child tables and UI preferences."""

    def __init__(self, session: Session) -> None:
        """Bind repository to an active database session.

        Args:
            session: SQLAlchemy session.
        """
        self.session = session

    def _validate_rename(self, old_code: str, new_code: str) -> CourseRecord:
        """Verify source exists, target is unused, and no running jobs belong to the source course.

        Args:
            old_code: Current course code.
            new_code: Proposed replacement course code.

        Returns:
            Existing `CourseRecord` row for `old_code`.

        Raises:
            ValueError: When validation preconditions fail.
        """
        if not old_code or not new_code or old_code == new_code:
            raise ValueError(f"不合法的課程代碼變更：{old_code!r} -> {new_code!r}")
        old_row = self.session.get(CourseRecord, old_code)
        if old_row is None:
            raise ValueError(f"找不到課程：{old_code}")
        if self.session.get(CourseRecord, new_code) is not None:
            raise ValueError(f"目標課程代碼已存在：{new_code}")
        running = (
            self.session.scalar(
                select(func.count())
                .select_from(ArtifactJobRecord)
                .where(
                    ArtifactJobRecord.course_code == old_code,
                    ArtifactJobRecord.status == JobStatus.RUNNING.value,
                )
            )
            or 0
        )
        if running:
            raise ValueError(f"課程 {old_code} 有執行中任務，無法更改代碼")
        return old_row

    def _matching_preferences(self, old_code: str) -> list[UiPreferenceRecord]:
        """Collect all UI preference rows referencing `old_code`.

        Args:
            old_code: Course code to search for.

        Returns:
            Matching `UiPreferenceRecord` rows.
        """
        rows: list[UiPreferenceRecord] = []
        course_pref = self.session.get(UiPreferenceRecord, "course")
        if course_pref is not None and course_pref.value in {old_code, json.dumps(old_code)}:
            rows.append(course_pref)
        exact_keys = (f"place:{old_code}", f"examNotice:{old_code}")
        rows.extend(
            self.session.scalars(
                select(UiPreferenceRecord).where(UiPreferenceRecord.key.in_(exact_keys))
            ).all()
        )
        audio_prefix = f"audio:{old_code}:"
        audio_rows = self.session.scalars(
            select(UiPreferenceRecord).where(UiPreferenceRecord.key.startswith(audio_prefix))
        ).all()
        rows.extend(audio_rows)
        return rows

    def preview_rename(self, old_code: str, new_code: str) -> dict[str, int]:
        """Count all rows across 11 child tables and UI preferences that a rename will update.

        Args:
            old_code: Current course code.
            new_code: Proposed replacement course code.

        Returns:
            Mapping of table name to affected row count.
        """
        self._validate_rename(old_code, new_code)
        counts: dict[str, int] = {}
        for model in (*_DIRECT_COURSE_TABLES, *_COMPOSITE_COURSE_TABLES):
            count = self.session.scalar(
                select(func.count()).select_from(model).where(model.course_code == old_code)
            )
            counts[str(model.__tablename__)] = int(count or 0)
        counts["ui_preferences"] = len(self._matching_preferences(old_code))
        return counts

    def _clone_course_row(self, old_row: CourseRecord, new_code: str) -> None:
        """Insert cloned `CourseRecord` under `new_code` with term/course_no updated when applicable.

        Args:
            old_row: Source `CourseRecord`.
            new_code: Target course code.
        """
        data = {col.name: getattr(old_row, col.name) for col in CourseRecord.__table__.columns}
        data["code"] = new_code
        parsed_term, parsed_no = split_course_code(new_code)
        if parsed_term:
            data["term"] = parsed_term
            data["course_no"] = parsed_no
        self.session.add(CourseRecord(**data))
        self.session.flush()

    def _update_composite_rows(self, old_code: str, new_code: str) -> None:
        """Update child tables whose primary keys embed `course_code`.

        Args:
            old_code: Previous course code.
            new_code: Replacement course code.
        """
        for rev in self.session.scalars(
            select(ReviewItemRecord).where(ReviewItemRecord.course_code == old_code)
        ).all():
            new_id = f"{rev.kind}:{new_code}:{rev.item_key}"
            self.session.execute(
                update(ReviewItemRecord)
                .where(ReviewItemRecord.id == rev.id)
                .values(id=new_id, course_code=new_code)
            )
        for exp in self.session.scalars(
            select(ExplanationRecord).where(ExplanationRecord.course_code == old_code)
        ).all():
            new_id = f"{new_code}:{exp.question_key}"
            self.session.execute(
                update(ExplanationRecord)
                .where(ExplanationRecord.id == exp.id)
                .values(id=new_id, course_code=new_code)
            )
        for kp in self.session.scalars(
            select(KeyPointsRecord).where(KeyPointsRecord.course_code == old_code)
        ).all():
            new_id = f"{new_code}:{kp.lecture_no}"
            self.session.execute(
                update(KeyPointsRecord)
                .where(KeyPointsRecord.id == kp.id)
                .values(id=new_id, course_code=new_code)
            )

    def _update_preferences(self, old_code: str, new_code: str) -> None:
        """Update UI preferences whose key or value references `old_code`.

        Args:
            old_code: Previous course code.
            new_code: Replacement course code.
        """
        for row in self._matching_preferences(old_code):
            if row.key == "course":
                new_val = new_code if row.value == old_code else json.dumps(new_code)
                self.session.execute(
                    update(UiPreferenceRecord).where(UiPreferenceRecord.key == "course").values(value=new_val)
                )
            elif row.key == f"place:{old_code}":
                self.session.execute(
                    update(UiPreferenceRecord)
                    .where(UiPreferenceRecord.key == row.key)
                    .values(key=f"place:{new_code}")
                )
            elif row.key == f"examNotice:{old_code}":
                self.session.execute(
                    update(UiPreferenceRecord)
                    .where(UiPreferenceRecord.key == row.key)
                    .values(key=f"examNotice:{new_code}")
                )
            elif row.key.startswith(f"audio:{old_code}:"):
                suffix = row.key[len(f"audio:{old_code}:") :]
                self.session.execute(
                    update(UiPreferenceRecord)
                    .where(UiPreferenceRecord.key == row.key)
                    .values(key=f"audio:{new_code}:{suffix}")
                )

    def _rewrite_job_output_paths(self, course_code: str, path_rewrites: list[tuple[str, str]]) -> None:
        """Update `artifact_jobs.output_file` prefixes moved during rename (Refs: ISSUE-067).

        Args:
            course_code: New course code.
            path_rewrites: Ordered `(old_prefix, new_prefix)` directory prefix pairs.
        """
        if not path_rewrites:
            return
        jobs = self.session.scalars(
            select(ArtifactJobRecord).where(
                ArtifactJobRecord.course_code == course_code,
                ArtifactJobRecord.output_file.is_not(None),
            )
        ).all()
        for job in jobs:
            val = job.output_file or ""
            for old_prefix, new_prefix in path_rewrites:
                if val == old_prefix or val.startswith(f"{old_prefix}/") or val.startswith(f"{old_prefix}\\"):
                    job.output_file = new_prefix + val[len(old_prefix) :]
                    break

    def rename_code(
        self,
        old_code: str,
        new_code: str,
        *,
        commit: bool = True,
        path_rewrites: list[tuple[str, str]] | None = None,
    ) -> dict[str, int]:
        """Rename `old_code` to `new_code` across `courses`, 11 child tables, and `ui_preferences`.

        Args:
            old_code: Current course code.
            new_code: Replacement course code.
            commit: Commit immediately when True; leave open for caller orchestration when False.
            path_rewrites: Optional `(old_prefix, new_prefix)` pairs to rewrite `artifact_jobs.output_file`.

        Returns:
            Mapping of table name to affected row count.
        """
        old_row = self._validate_rename(old_code, new_code)
        counts = self.preview_rename(old_code, new_code)
        self._clone_course_row(old_row, new_code)
        for model in _DIRECT_COURSE_TABLES:
            self.session.execute(
                update(model).where(model.course_code == old_code).values(course_code=new_code)
            )
        if path_rewrites:
            self._rewrite_job_output_paths(new_code, path_rewrites)
        self._update_composite_rows(old_code, new_code)
        self._update_preferences(old_code, new_code)
        self.session.execute(delete(CourseRecord).where(CourseRecord.code == old_code))
        self.session.flush()
        self.session.expire_all()
        if commit:
            self.session.commit()
        logger.info("Renamed course code in DB: %s -> %s (commit=%s)", old_code, new_code, commit)
        return counts

    def commit(self) -> None:
        """Commit the active session transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Roll back the active session transaction and expire cached ORM objects."""
        self.session.rollback()
        self.session.expire_all()

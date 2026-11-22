"""Database adapter for reading and updating course paths during study-layout migration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.models import ArtifactJobRecord, CourseRecord, LectureRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigratableCourse:
    """Plain DTO representing a course row eligible for study-layout migration.

    Attributes:
        code: Course code.
        name: Course name.
        source_dir: Current source directory.
        term: Existing term value if set.
        subject: Existing subject value if set.
        study_dir: Existing study directory if set.
    """

    code: str
    name: str
    source_dir: str
    term: str
    subject: str
    study_dir: str


class StudyMigrationRepository:
    """Reads and updates DB course/lecture/job paths for study-layout migration."""

    def __init__(self, session: Session) -> None:
        """Bind repository to an active SQLAlchemy session.

        Args:
            session: Open SQLAlchemy session.
        """
        self.session = session

    def list_courses(self) -> list[MigratableCourse]:
        """Return all courses ordered by code.

        Returns:
            List of `MigratableCourse` DTOs.
        """
        rows = self.session.scalars(select(CourseRecord).order_by(CourseRecord.code)).all()
        return [
            MigratableCourse(
                code=r.code,
                name=r.name,
                source_dir=r.source_dir,
                term=r.term,
                subject=r.subject,
                study_dir=r.study_dir,
            )
            for r in rows
        ]

    def apply_course_migration(
        self, code: str, term: str, subject: str, study_dir: Path, new_notes_dir: Path
    ) -> None:
        """Update `courses`, `lectures`, and `artifact_jobs` paths for one migrated course.

        Args:
            code: Course code.
            term: Resolved academic term.
            subject: Resolved subject name.
            study_dir: New unified study directory.
            new_notes_dir: New `<study_dir>/03 Notes/NotebookLM` directory.
        """
        record = self.session.get(CourseRecord, code)
        if record is None:
            return
        old_out_prefix = str(Path(record.source_dir).parent.parent.parent / "output" / "courses" / code)
        record.term = term
        record.subject = subject
        record.study_dir = str(study_dir)
        record.source_dir = str(study_dir)

        for lec in self.session.scalars(select(LectureRecord).where(LectureRecord.course_code == code)).all():
            if not lec.relative_path and (study_dir / "02 Handout" / lec.filename).is_file():
                lec.category = "02 Handout"
                lec.relative_path = f"02 Handout/{lec.filename}"

        for job in self.session.scalars(
            select(ArtifactJobRecord).where(ArtifactJobRecord.course_code == code)
        ).all():
            if job.output_file and old_out_prefix in job.output_file:
                job.output_file = job.output_file.replace(old_out_prefix, str(new_notes_dir))

    def commit(self) -> None:
        """Commit pending DB updates."""
        self.session.commit()

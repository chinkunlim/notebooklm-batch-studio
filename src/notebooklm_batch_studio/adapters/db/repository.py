"""Database repositories: encapsulate data access, converting ORM records to domain entities."""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.mappers import to_domain_course, to_domain_lecture
from notebooklm_batch_studio.adapters.db.models import (
    ArtifactJobRecord,
    CourseQANoteRecord,
    CourseRecord,
    ExplanationRecord,
    KeyPointsRecord,
    LectureRecord,
    QuizAttemptRecord,
    QuizMistakeRecord,
    ReviewItemRecord,
    StudyProgressRecord,
    TutorMessageRecord,
    UiPreferenceRecord,
    utc_now,
)
from notebooklm_batch_studio.adapters.db.queue_repository import QueueRepository as QueueRepository
from notebooklm_batch_studio.domain.models import Course, CourseStatus, GenerationOptions, Lecture

logger = logging.getLogger(__name__)


_COURSE_OWNED_MODELS: tuple[Any, ...] = (
    QuizMistakeRecord,
    QuizAttemptRecord,
    StudyProgressRecord,
    ReviewItemRecord,
    ExplanationRecord,
    KeyPointsRecord,
    TutorMessageRecord,
    CourseQANoteRecord,
    ArtifactJobRecord,
    LectureRecord,
)


class CourseRepository:
    """Database access for courses and lecture source mappings."""

    def __init__(self, session: Session) -> None:
        """Bind repository to an active database session.

        Args:
            session: SQLAlchemy session.
        """
        self.session = session

    def _update_lectures(self, code: str, lectures: list[Lecture]) -> None:
        """Replace all lectures for a course, keeping upload state of PDFs whose content is unchanged.

        A rescanned lecture carries no source id; if a stored lecture has the same sha256 its
        Gemini Notebook source id and upload status are kept, so re-registering never re-uploads it.
        Refs: ISSUE-006

        Args:
            code: Course code.
            lectures: List of lecture entities to persist.
        """
        stmt = select(LectureRecord).where(LectureRecord.course_code == code)
        uploaded = {r.sha256: r for r in self.session.scalars(stmt).all() if r.source_id}
        self.session.execute(delete(LectureRecord).where(LectureRecord.course_code == code))
        for lecture in lectures:
            prev = uploaded.get(lecture.sha256) if lecture.source_id is None else None
            if prev is not None:
                lecture = dataclasses.replace(
                    lecture, source_id=prev.source_id, upload_status=prev.upload_status, error_message=None
                )
            self.session.add(
                LectureRecord(
                    course_code=code,
                    no=lecture.no,
                    topic=lecture.topic,
                    filename=lecture.filename,
                    sha256=lecture.sha256,
                    source_id=lecture.source_id,
                    upload_status=lecture.upload_status,
                    error_message=lecture.error_message,
                    category=lecture.category,
                    relative_path=lecture.relative_path,
                )
            )

    def update_lecture_upload_status(self, code: str, lecture_no: int, status: str, **details: Any) -> None:
        """Update upload state, source ID, and error message for a lecture PDF.

        Args:
            code: Course code.
            lecture_no: Sequence number of the lecture.
            status: Status string (pending, uploading, parsing, ready, failed).
            **details: Optional `source_id` (`str | None`) and `error_message` (`str | None`).
        """
        source_id = details.get("source_id")
        error_message = details.get("error_message")
        stmt = select(LectureRecord).where(LectureRecord.course_code == code, LectureRecord.no == lecture_no)
        record = self.session.scalars(stmt).first()
        if record:
            record.upload_status = status
            if "source_id" in details:
                record.source_id = source_id
            record.error_message = error_message
            self.session.flush()
            self.session.commit()

    def _create_course_record(self, course: Course) -> CourseRecord:
        """Create and stage a new ORM CourseRecord for `course`.

        Args:
            course: Domain course entity.

        Returns:
            Newly staged CourseRecord.
        """
        record = CourseRecord(
            code=course.code,
            name=course.name,
            source_dir=course.source_dir,
            notebook_id=course.notebook_id,
            profile=course.profile.value,
            language=course.language,
            exam_date=course.exam_date,
            watch=course.watch,
            mock_exam_questions=course.mock_exam_questions,
            # Later re-registrations keep the stored options (see update_generation_options).
            generation_options=json.dumps(dataclasses.asdict(course.generation_options)),
            paused=course.paused,
            reuse_notebook=course.reuse_notebook,
            term=course.term,
            subject=course.subject,
            study_dir=course.study_dir,
            status=course.status.value,
            course_no=course.course_no,
        )
        self.session.add(record)
        return record

    def _apply_course_updates(self, existing: CourseRecord, course: Course) -> None:
        """Update fields of an existing CourseRecord in place, guarding against code collisions.

        Args:
            existing: Persisted CourseRecord row.
            course: Updated domain course entity.
        """
        # Refs: ISSUE-037 — Different name + different source_dir indicates a code collision.
        if existing.name != course.name and existing.source_dir != course.source_dir:
            logger.warning(
                "Course code %s collision: %s (%s) vs existing %s (%s). Resetting notebook_id.",
                course.code,
                course.name,
                course.source_dir,
                existing.name,
                existing.source_dir,
            )
            existing.notebook_id = course.notebook_id
        elif course.notebook_id:
            existing.notebook_id = course.notebook_id
        existing.name = course.name
        existing.source_dir = course.source_dir
        existing.profile = course.profile.value
        existing.language = course.language
        if course.exam_date:  # a rescan without course.toml keeps a date set in the web app
            existing.exam_date = course.exam_date
        existing.watch = course.watch
        existing.mock_exam_questions = course.mock_exam_questions
        if course.term:
            existing.term = course.term
        if course.subject:
            existing.subject = course.subject
        if course.study_dir:
            existing.study_dir = course.study_dir
        existing.status = course.status.value
        if course.course_no:
            existing.course_no = course.course_no
        existing.updated_at = utc_now()

    def save_course(self, course: Course) -> None:
        """Insert or update a course entity and its lectures.

        Args:
            course: Domain course entity to persist.
        """
        existing = self.session.get(CourseRecord, course.code)
        if existing is None:
            existing = self._create_course_record(course)
        else:
            self._apply_course_updates(existing, course)

        # Preserve any custom artifact selection on folder rescans that carry an empty selection.
        if course.selected_chapter_artifacts or course.selected_course_artifacts:
            existing.selected_chapter_artifacts = json.dumps(course.selected_chapter_artifacts)
            existing.selected_course_artifacts = json.dumps(course.selected_course_artifacts)
        self._update_lectures(course.code, course.lectures)
        self.session.flush()
        self.session.commit()

    def get_course(self, code: str) -> Course | None:
        """Retrieve a course by its code identifier.

        Args:
            code: The unique course code (e.g. BIO101).

        Returns:
            The domain Course entity, or None if not found.
        """
        record = self.session.get(CourseRecord, code)
        if record is None:
            return None
        stmt = select(LectureRecord).where(LectureRecord.course_code == code).order_by(LectureRecord.no.asc())
        lectures = [to_domain_lecture(r) for r in self.session.scalars(stmt)]
        return to_domain_course(record, lectures)

    def list_courses(self, status: CourseStatus | None = None) -> list[Course]:
        """List courses registered in the system, optionally filtered by status.

        Args:
            status: Optional `CourseStatus` filter (`active` or `archived`).

        Returns:
            List of domain Course entities.
        """
        course_stmt = select(CourseRecord).order_by(CourseRecord.code.asc())
        if status is not None:
            course_stmt = course_stmt.where(CourseRecord.status == status.value)
        records = self.session.scalars(course_stmt).all()
        result: list[Course] = []
        for r in records:
            stmt = (
                select(LectureRecord)
                .where(LectureRecord.course_code == r.code)
                .order_by(LectureRecord.no.asc())
            )
            lectures = [to_domain_lecture(lec) for lec in self.session.scalars(stmt)]
            result.append(to_domain_course(r, lectures))
        return result

    def update_artifact_selection(self, code: str, chapter: list[str], whole: list[str]) -> None:
        """Replace a course's chosen per-lecture and course-wide artifact types.

        Args:
            code: Course code.
            chapter: Per-lecture artifact type values.
            whole: Course-wide artifact type values.
        """
        record = self.session.get(CourseRecord, code)
        if record:
            record.selected_chapter_artifacts = json.dumps(chapter)
            record.selected_course_artifacts = json.dumps(whole)
            record.updated_at = utc_now()
            self.session.flush()
            self.session.commit()

    def count_learning_records(self, code: str) -> dict[str, int]:
        """Count removable learning records per table for a course.

        Args:
            code: Course code.

        Returns:
            Mapping of table name to record count.
        """
        tables: tuple[tuple[str, Any], ...] = (
            ("quiz_attempts", QuizAttemptRecord),
            ("quiz_mistakes", QuizMistakeRecord),
            ("study_progress", StudyProgressRecord),
            ("review_items", ReviewItemRecord),
            ("explanations", ExplanationRecord),
            ("key_points", KeyPointsRecord),
            ("tutor_messages", TutorMessageRecord),
            ("course_qa_notes", CourseQANoteRecord),
        )
        counts: dict[str, int] = {}
        for name, model in tables:
            stmt = select(func.count()).select_from(model).where(model.course_code == code)
            counts[name] = int(self.session.execute(stmt).scalar_one() or 0)
        return counts

    def delete_course(self, code: str) -> int:
        """Delete a course and everything recorded for it in this database.

        Gemini Notebook is not touched; only local records (jobs, lectures, study history) go.

        Args:
            code: Course code.

        Returns:
            Number of jobs that were removed.
        """
        removed = 0
        for model in _COURSE_OWNED_MODELS:
            result = self.session.execute(delete(model).where(model.course_code == code))
            if model is ArtifactJobRecord:
                removed = int(getattr(result, "rowcount", 0) or 0)
        self.session.execute(
            delete(UiPreferenceRecord).where(
                or_(
                    (UiPreferenceRecord.key == "course")
                    & UiPreferenceRecord.value.in_([code, json.dumps(code)]),
                    UiPreferenceRecord.key.in_([f"place:{code}", f"examNotice:{code}"]),
                    UiPreferenceRecord.key.startswith(f"audio:{code}:"),
                )
            )
        )
        self.session.execute(delete(CourseRecord).where(CourseRecord.code == code))
        self.session.flush()
        self.session.commit()
        return removed

    def set_course_paused(self, code: str, paused: bool) -> None:
        """Pause or resume one course in the queue.

        Args:
            code: Course code.
            paused: True to hold the course's jobs, False to let them run.
        """
        record = self.session.get(CourseRecord, code)
        if record:
            record.paused = paused
            record.updated_at = utc_now()
            self.session.flush()
            self.session.commit()

    def update_course_basics(
        self, code: str, language: str, mock_exam_questions: int, exam_date: str | None = None
    ) -> None:
        """Change a course's output language, mock exam question target and exam date.

        Args:
            code: Course code.
            language: 'zh-TW', 'en' or 'bilingual'.
            mock_exam_questions: Target number of questions in the course mock exam.
            exam_date: 'YYYY-MM-DD', or None for no date.
        """
        record = self.session.get(CourseRecord, code)
        if record:
            record.language = language
            record.mock_exam_questions = mock_exam_questions
            record.exam_date = exam_date
            record.updated_at = utc_now()
            self.session.flush()
            self.session.commit()

    def update_course_name(self, code: str, name: str) -> bool:
        """Change only a course's display name (Refs: SPEC-016).

        Args:
            code: Course code.
            name: New display name (already validated by the caller).

        Returns:
            True when the course exists and was updated.
        """
        record = self.session.get(CourseRecord, code)
        if record is None:
            return False
        record.name = name
        record.updated_at = utc_now()
        self.session.commit()
        return True

    def update_generation_options(self, code: str, options: GenerationOptions) -> None:
        """Store a course's Gemini Notebook generation options.

        Args:
            code: Course code.
            options: Options to persist.
        """
        record = self.session.get(CourseRecord, code)
        if record:
            record.generation_options = json.dumps(dataclasses.asdict(options))
            record.updated_at = utc_now()
            self.session.flush()
            self.session.commit()

    def get_study_activity(
        self, code: str
    ) -> tuple[set[tuple[int | None, str]], set[tuple[int | None, str]], set[int | None]]:
        """Query student progress marks, quiz attempts, and flashcard reviews for one course.

        Args:
            code: Course code.

        Returns:
            Tuple of (study_marks, attempted_quizzes, reviewed_flashcard_lectures).
        """
        marks_stmt = select(StudyProgressRecord.lecture_no, StudyProgressRecord.step).where(
            StudyProgressRecord.course_code == code
        )
        marks = {(row[0], row[1]) for row in self.session.execute(marks_stmt)}
        quiz_stmt = select(QuizAttemptRecord.lecture_no, QuizAttemptRecord.quiz_variant).where(
            QuizAttemptRecord.course_code == code
        )
        attempted = {(row[0], row[1]) for row in self.session.execute(quiz_stmt)}
        rev_stmt = select(ReviewItemRecord.lecture_no).where(
            ReviewItemRecord.course_code == code,
            ReviewItemRecord.kind == "flashcard",
            ReviewItemRecord.last_reviewed_at.is_not(None),
        )
        reviewed = set(self.session.scalars(rev_stmt.distinct()))
        return marks, attempted, reviewed

    def update_notebook_id(self, code: str, notebook_id: str) -> None:
        """Update the linked Gemini Notebook notebook ID for a course.

        Args:
            code: Course code.
            notebook_id: Google Gemini Notebook notebook ID.
        """
        record = self.session.get(CourseRecord, code)
        if record:
            record.notebook_id = notebook_id
            record.updated_at = utc_now()
            self.session.flush()
            self.session.commit()

    def update_lecture_source_id(self, code: str, lecture_no: int, source_id: str) -> None:
        """Update the Gemini Notebook source ID for a lecture.

        Args:
            code: Course code.
            lecture_no: Sequence number of the lecture.
            source_id: Uploaded source ID from Gemini Notebook.
        """
        stmt = select(LectureRecord).where(LectureRecord.course_code == code, LectureRecord.no == lecture_no)
        record = self.session.scalars(stmt).first()
        if record:
            record.source_id = source_id
            self.session.flush()
            self.session.commit()

    def update_profile(self, code: str, profile: str) -> None:
        """Update the active profile for a course.

        Args:
            code: Course code.
            profile: New profile string.
        """
        record = self.session.get(CourseRecord, code)
        if record:
            record.profile = profile
            record.updated_at = utc_now()
            self.session.flush()
            self.session.commit()

"""Database repositories: encapsulate data access, converting ORM records to domain entities."""

from __future__ import annotations

import dataclasses
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.models import (
    ArtifactJobRecord,
    CourseRecord,
    GreetingRecord,
    LectureRecord,
    QuotaRecord,
    utc_now,
)
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    GreetingResult,
    JobStatus,
    Lecture,
    ProfileName,
)


def _to_domain_lecture(record: LectureRecord) -> Lecture:
    """Convert a LectureRecord ORM instance to a pure domain Lecture object.

    Args:
        record: Database lecture record.

    Returns:
        Immutable domain Lecture entity.
    """
    return Lecture(
        no=record.no,
        topic=record.topic,
        filename=record.filename,
        sha256=record.sha256,
        source_id=record.source_id,
        upload_status=getattr(record, "upload_status", "pending") or "pending",
        error_message=getattr(record, "error_message", None),
    )


def _to_domain_course(record: CourseRecord, lectures: list[Lecture]) -> Course:
    """Convert a CourseRecord ORM instance to a pure domain Course object.

    Args:
        record: Database course record.
        lectures: Associated domain lecture objects.

    Returns:
        Immutable domain Course entity.
    """
    return Course(
        code=record.code,
        name=record.name,
        source_dir=record.source_dir,
        notebook_id=record.notebook_id,
        profile=(
            ProfileName(record.profile)
            if record.profile in ProfileName._value2member_map_
            else ProfileName.FULL
        ),
        language=record.language,
        exam_date=record.exam_date,
        watch=record.watch,
        mock_exam_questions=record.mock_exam_questions,
        lectures=lectures,
    )


def _to_domain_job(record: ArtifactJobRecord) -> ArtifactJob:
    """Convert an ArtifactJobRecord ORM instance to a pure domain ArtifactJob object.

    Args:
        record: Database job record.

    Returns:
        Immutable domain ArtifactJob entity.
    """
    return ArtifactJob(
        id=record.id,
        course_code=record.course_code,
        lecture_no=record.lecture_no,
        artifact_type=ArtifactType(record.artifact_type),
        status=JobStatus(record.status),
        attempts=record.attempts,
        worker_id=record.worker_id,
        error_message=record.error_message,
        output_file=record.output_file,
        custom_prompt=getattr(record, "custom_prompt", None),
        style_options=getattr(record, "style_options", None),
        interactive_path=getattr(record, "interactive_path", None),
        source_origin=getattr(record, "source_origin", "auto"),
        quota_blocked_at=record.quota_blocked_at,
        cooldown_until=record.cooldown_until,
        created_at=record.created_at,
        updated_at=record.updated_at,
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
        NotebookLM source id and upload status are kept, so re-registering never re-uploads it.
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
                )
            )

    def update_lecture_upload_status(
        self,
        code: str,
        lecture_no: int,
        status: str,
        source_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update upload state, source ID, and error message for a lecture PDF.

        Args:
            code: Course code.
            lecture_no: Sequence number of the lecture.
            status: Status string (pending, uploading, parsing, ready, failed).
            source_id: Optional NotebookLM source ID when ready.
            error_message: Optional failure explanation.
        """
        stmt = select(LectureRecord).where(LectureRecord.course_code == code, LectureRecord.no == lecture_no)
        record = self.session.scalars(stmt).first()
        if record:
            record.upload_status = status
            if source_id:
                record.source_id = source_id
            record.error_message = error_message
            self.session.flush()
            self.session.commit()

    def save_course(self, course: Course) -> None:
        """Insert or update a course entity and its lectures.

        Args:
            course: Domain course entity to persist.
        """
        existing = self.session.get(CourseRecord, course.code)
        if existing is None:
            existing = CourseRecord(
                code=course.code,
                name=course.name,
                source_dir=course.source_dir,
                notebook_id=course.notebook_id,
                profile=course.profile.value,
                language=course.language,
                exam_date=course.exam_date,
                watch=course.watch,
                mock_exam_questions=course.mock_exam_questions,
            )
            self.session.add(existing)
        else:
            existing.name = course.name
            existing.source_dir = course.source_dir
            if course.notebook_id:
                existing.notebook_id = course.notebook_id
            existing.profile = course.profile.value
            existing.language = course.language
            existing.exam_date = course.exam_date
            existing.watch = course.watch
            existing.mock_exam_questions = course.mock_exam_questions
            existing.updated_at = utc_now()

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
        lectures = [_to_domain_lecture(r) for r in self.session.scalars(stmt)]
        return _to_domain_course(record, lectures)

    def list_courses(self) -> list[Course]:
        """List all courses registered in the system.

        Returns:
            List of domain Course entities.
        """
        records = self.session.scalars(select(CourseRecord).order_by(CourseRecord.code.asc())).all()
        result: list[Course] = []
        for r in records:
            stmt = (
                select(LectureRecord)
                .where(LectureRecord.course_code == r.code)
                .order_by(LectureRecord.no.asc())
            )
            lectures = [_to_domain_lecture(lec) for lec in self.session.scalars(stmt)]
            result.append(_to_domain_course(r, lectures))
        return result

    def update_notebook_id(self, code: str, notebook_id: str) -> None:
        """Update the linked NotebookLM notebook ID for a course.

        Args:
            code: Course code.
            notebook_id: Google NotebookLM notebook ID.
        """
        record = self.session.get(CourseRecord, code)
        if record:
            record.notebook_id = notebook_id
            record.updated_at = utc_now()
            self.session.flush()
            self.session.commit()

    def update_lecture_source_id(self, code: str, lecture_no: int, source_id: str) -> None:
        """Update the NotebookLM source ID for a lecture.

        Args:
            code: Course code.
            lecture_no: Sequence number of the lecture.
            source_id: Uploaded source ID from NotebookLM.
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


class QueueRepository:
    """Database access for the parallel task queue and quota tracking."""

    def __init__(self, session: Session) -> None:
        """Bind repository to an active database session.

        Args:
            session: SQLAlchemy session.
        """
        self.session = session

    def enqueue_jobs(self, jobs: list[ArtifactJob]) -> int:
        """Add new artifact jobs to the queue, skipping duplicates already present.

        Args:
            jobs: List of domain ArtifactJob entities to enqueue.

        Returns:
            Number of newly added jobs.
        """
        added_count = 0
        for job in jobs:
            stmt = select(ArtifactJobRecord).where(
                ArtifactJobRecord.course_code == job.course_code,
                ArtifactJobRecord.lecture_no == job.lecture_no,
                ArtifactJobRecord.artifact_type == job.artifact_type.value,
            )
            existing = self.session.scalars(stmt).first()
            if existing is None:
                record = ArtifactJobRecord(
                    id=job.id,
                    course_code=job.course_code,
                    lecture_no=job.lecture_no,
                    artifact_type=job.artifact_type.value,
                    status=job.status.value,
                    attempts=job.attempts,
                    worker_id=job.worker_id,
                    error_message=job.error_message,
                    output_file=job.output_file,
                    custom_prompt=job.custom_prompt,
                    style_options=job.style_options,
                    interactive_path=job.interactive_path,
                    source_origin=job.source_origin,
                )
                self.session.add(record)
                added_count += 1
        self.session.flush()
        self.session.commit()
        return added_count

    def claim_next_job(
        self, worker_id: str, excluded_types: set[ArtifactType] | None = None
    ) -> ArtifactJob | None:
        """Atomically claim the next eligible PENDING job for a worker.

        Args:
            worker_id: Identifier of the worker claiming the job.
            excluded_types: Artifact types that are currently blocked by quota limits.

        Returns:
            The claimed domain ArtifactJob, or None if no eligible job is waiting.
        """
        stmt = select(ArtifactJobRecord).where(ArtifactJobRecord.status == JobStatus.PENDING.value)
        if excluded_types:
            excluded_str = [t.value for t in excluded_types]
            stmt = stmt.where(ArtifactJobRecord.artifact_type.not_in(excluded_str))

        # Order by lecture number (sequential order per course) then creation time
        stmt = stmt.order_by(
            ArtifactJobRecord.lecture_no.asc().nulls_last(),
            ArtifactJobRecord.created_at.asc(),
        )
        record = self.session.scalars(stmt).first()

        if record is None:
            return None

        record.status = JobStatus.RUNNING.value
        record.worker_id = worker_id
        record.attempts += 1
        record.updated_at = utc_now()
        self.session.flush()
        self.session.commit()
        return _to_domain_job(record)

    def complete_job(self, job_id: str, output_file: str, interactive_path: str | None = None) -> None:
        """Mark a job as successfully completed.

        Args:
            job_id: Task UUID.
            output_file: Path of the generated output file.
            interactive_path: Optional path to interactive HTML output.
        """
        record = self.session.get(ArtifactJobRecord, job_id)
        if record:
            record.status = JobStatus.DONE.value
            record.output_file = output_file
            if interactive_path:
                record.interactive_path = interactive_path
            record.error_message = None
            record.worker_id = None
            record.updated_at = utc_now()
            self.session.flush()
            self.session.commit()

    def mark_needs_review(self, job_id: str, output_file: str, message: str) -> None:
        """Mark a job as NEEDS_REVIEW; it is not retried until the user retries it.

        Args:
            job_id: Task UUID.
            output_file: Path of the quarantined output file.
            message: Why the output needs review.
        """
        record = self.session.get(ArtifactJobRecord, job_id)
        if record:
            record.status = JobStatus.NEEDS_REVIEW.value
            record.output_file = output_file
            record.error_message = message
            record.worker_id = None
            record.updated_at = utc_now()
            self.session.flush()
            self.session.commit()

    def fail_job(self, job_id: str, error_message: str, max_attempts: int = 3) -> None:
        """Handle a job failure, retrying if under max_attempts or marking FAILED.

        Args:
            job_id: Task UUID.
            error_message: Detailed failure explanation.
            max_attempts: Maximum retry threshold before permanent failure.
        """
        record = self.session.get(ArtifactJobRecord, job_id)
        if record:
            record.error_message = error_message
            record.worker_id = None
            record.updated_at = utc_now()
            if record.attempts < max_attempts:
                record.status = JobStatus.PENDING.value
            else:
                record.status = JobStatus.FAILED.value
            self.session.flush()
            self.session.commit()

    def block_job_quota(self, job_id: str, artifact_type: ArtifactType, cooldown_seconds: int = 3600) -> None:
        """Mark a job as waiting for quota refresh and set cooldown timer.

        Args:
            job_id: Task UUID.
            artifact_type: The artifact type that hit quota.
            cooldown_seconds: Duration before quota probe should attempt wake up.
        """
        now = utc_now()
        cooldown_time = now + timedelta(seconds=cooldown_seconds)
        record = self.session.get(ArtifactJobRecord, job_id)
        if record:
            # A quota wait is not a failed attempt: give back the attempt taken at claim. Refs: ISSUE-008
            record.attempts = max(0, record.attempts - 1)
            record.status = JobStatus.QUOTA_WAIT.value
            record.quota_blocked_at = now
            record.cooldown_until = cooldown_time
            record.worker_id = None
            record.updated_at = now

        # Update quota record table
        quota = self.session.get(QuotaRecord, artifact_type.value)
        if quota is None:
            quota = QuotaRecord(
                artifact_type=artifact_type.value,
                used_today=1,
                last_blocked_at=now,
                cooldown_until=cooldown_time,
            )
            self.session.add(quota)
        else:
            quota.last_blocked_at = now
            quota.cooldown_until = cooldown_time

        self.session.flush()
        self.session.commit()

    def refresh_quota_wait(self, artifact_type: ArtifactType | None = None) -> int:
        """Reset jobs in QUOTA_WAIT state back to PENDING when cooldown has passed.

        Args:
            artifact_type: Specific artifact type to reset, or None for all eligible.

        Returns:
            Number of jobs awakened back to PENDING.
        """
        now = utc_now()
        stmt = select(ArtifactJobRecord).where(ArtifactJobRecord.status == JobStatus.QUOTA_WAIT.value)
        if artifact_type is not None:
            stmt = stmt.where(ArtifactJobRecord.artifact_type == artifact_type.value)
        else:
            stmt = stmt.where(ArtifactJobRecord.cooldown_until <= now)

        records = self.session.scalars(stmt).all()
        for r in records:
            r.status = JobStatus.PENDING.value
            r.worker_id = None
            r.updated_at = now
        self.session.flush()
        self.session.commit()
        return len(records)

    def list_jobs(self, course_code: str | None = None, status: JobStatus | None = None) -> list[ArtifactJob]:
        """Query jobs filtered by course or status.

        Args:
            course_code: Filter by course identifier.
            status: Filter by job state.

        Returns:
            List of matching domain ArtifactJob entities.
        """
        stmt = select(ArtifactJobRecord)
        if course_code:
            stmt = stmt.where(ArtifactJobRecord.course_code == course_code)
        if status:
            stmt = stmt.where(ArtifactJobRecord.status == status.value)
        stmt = stmt.order_by(ArtifactJobRecord.created_at.asc())
        return [_to_domain_job(r) for r in self.session.scalars(stmt)]

    def get_job(self, job_id: str) -> ArtifactJob | None:
        """Retrieve a specific job by its ID.

        Args:
            job_id: Task UUID.

        Returns:
            Domain ArtifactJob entity or None.
        """
        record = self.session.get(ArtifactJobRecord, job_id)
        return _to_domain_job(record) if record else None

    def retry_job(self, job_id: str) -> bool:
        """Reset a job back to PENDING status to allow re-execution.

        Args:
            job_id: Task UUID.

        Returns:
            True if the job was found and reset, False otherwise.
        """
        record = self.session.get(ArtifactJobRecord, job_id)
        if record is None:
            return False
        record.status = JobStatus.PENDING.value
        record.worker_id = None
        record.error_message = None
        record.updated_at = utc_now()
        self.session.flush()
        self.session.commit()
        return True

    def update_job_prompt(self, job_id: str, prompt: str) -> bool:
        """Update the custom generation prompt for a specific job.

        Args:
            job_id: Task UUID.
            prompt: New custom prompt string.

        Returns:
            True if job was found and updated, False otherwise.
        """
        record = self.session.get(ArtifactJobRecord, job_id)
        if record is None:
            return False
        record.custom_prompt = prompt
        record.updated_at = utc_now()
        self.session.flush()
        self.session.commit()
        return True

    def count_by_status(self, course_code: str | None = None) -> dict[JobStatus, int]:
        """Compute the breakdown of jobs across all statuses.

        Args:
            course_code: Optional course filter.

        Returns:
            Mapping from JobStatus to integer count.
        """
        stmt = select(ArtifactJobRecord.status, func.count(ArtifactJobRecord.id))
        if course_code:
            stmt = stmt.where(ArtifactJobRecord.course_code == course_code)
        stmt = stmt.group_by(ArtifactJobRecord.status)
        counts = {status: 0 for status in JobStatus}
        for status_str, count in self.session.execute(stmt):
            try:
                counts[JobStatus(status_str)] = count
            except ValueError:
                pass
        return counts


class GreetingRepository:
    """Database access for greetings (for backward-compatibility)."""

    def __init__(self, session: Session) -> None:
        """Bind repository to an active session.

        Args:
            session: SQLAlchemy session.
        """
        self.session = session

    def add(self, user_name: str, result: GreetingResult) -> int:
        """Store one greeting.

        Args:
            user_name: Name that was greeted.
            result: Greeting produced by the service layer.

        Returns:
            The new row ID.
        """
        record = GreetingRecord(user_name=user_name, message=result.message)
        self.session.add(record)
        self.session.flush()
        return record.id

    def recent(self, limit: int = 20, environment: str = "") -> list[GreetingResult]:
        """Return the newest greetings first.

        Args:
            limit: Maximum number of rows.
            environment: Environment name copied into domain objects.

        Returns:
            Greetings as domain objects.
        """
        stmt = select(GreetingRecord).order_by(GreetingRecord.id.desc()).limit(limit)
        rows = self.session.scalars(stmt)
        return [GreetingResult(message=r.message, environment=environment) for r in rows]

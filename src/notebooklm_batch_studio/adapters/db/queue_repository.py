"""Queue and quota database repository split out of `repository.py`."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.mappers import to_domain_job
from notebooklm_batch_studio.adapters.db.models import (
    ArtifactJobRecord,
    CourseRecord,
    QuotaRecord,
    utc_now,
)
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, JobStatus

logger = logging.getLogger(__name__)


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
                ArtifactJobRecord.version == job.version,
            )
            if self.session.scalars(stmt).first() is None:
                self.session.add(self._to_job_record(job))
                added_count += 1
        self.session.flush()
        self.session.commit()
        return added_count

    @staticmethod
    def _to_job_record(job: ArtifactJob) -> ArtifactJobRecord:
        """Construct an ORM `ArtifactJobRecord` from a domain entity.

        Args:
            job: Domain job entity.

        Returns:
            Unsaved ORM record.
        """
        return ArtifactJobRecord(
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
            version=job.version,
        )

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
        stmt = select(ArtifactJobRecord).where(
            ArtifactJobRecord.status == JobStatus.PENDING.value,
            ArtifactJobRecord.course_code.not_in(
                select(CourseRecord.code).where(CourseRecord.paused.is_(True))
            ),
        )
        if excluded_types:
            stmt = stmt.where(ArtifactJobRecord.artifact_type.not_in([t.value for t in excluded_types]))

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
        return to_domain_job(record)

    def update_job_style_options(self, job_id: str, style_options: str | None) -> None:
        """Store one job's own option overrides (JSON), or clear them with None.

        Args:
            job_id: Task UUID.
            style_options: JSON object text, or None.
        """
        record = self.session.get(ArtifactJobRecord, job_id)
        if record:
            record.style_options = style_options
            record.updated_at = utc_now()
            self.session.flush()
            self.session.commit()

    def record_artifact_ids(self, job_id: str, artifact_ids: list[str]) -> None:
        """Remember which Gemini Notebook artifacts / notes a job produced. Refs: ADR-005

        Args:
            job_id: Task UUID.
            artifact_ids: Artifact or note ids returned by the generate calls.
        """
        record = self.session.get(ArtifactJobRecord, job_id)
        if record:
            record.artifact_ids = json.dumps(list(artifact_ids))
            self.session.flush()
            self.session.commit()

    def set_types_status(
        self,
        course_code: str,
        artifact_types: list[str],
        from_statuses: list[JobStatus],
        to_status: JobStatus,
    ) -> int:
        """Move a course's jobs of the given types from some statuses to another.

        Args:
            course_code: Course code.
            artifact_types: Artifact type values to change.
            from_statuses: Only jobs currently in these statuses change.
            to_status: New status.

        Returns:
            Number of jobs changed.
        """
        if not artifact_types:
            return 0
        stmt = select(ArtifactJobRecord).where(
            ArtifactJobRecord.course_code == course_code,
            ArtifactJobRecord.artifact_type.in_(artifact_types),
            ArtifactJobRecord.status.in_([s.value for s in from_statuses]),
        )
        records = self.session.scalars(stmt).all()
        for record in records:
            record.status = to_status.value
            record.updated_at = utc_now()
        self.session.flush()
        self.session.commit()
        return len(records)

    def max_version(self, course_code: str, lecture_no: int | None, artifact_type: ArtifactType) -> int:
        """Return the highest version generated so far for one artifact slot.

        Args:
            course_code: Course code.
            lecture_no: Lecture number, or None for course-wide artifacts.
            artifact_type: Artifact type.

        Returns:
            Highest version number, or 0 when the slot has no job yet.
        """
        stmt = select(func.max(ArtifactJobRecord.version)).where(
            ArtifactJobRecord.course_code == course_code,
            ArtifactJobRecord.lecture_no == lecture_no,
            ArtifactJobRecord.artifact_type == artifact_type.value,
        )
        return int(self.session.scalar(stmt) or 0)

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
            record.status = (
                JobStatus.PENDING.value if record.attempts < max_attempts else JobStatus.FAILED.value
            )
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

        quota = self.session.get(QuotaRecord, artifact_type.value)
        if quota is None:
            self.session.add(
                QuotaRecord(
                    artifact_type=artifact_type.value,
                    used_today=1,
                    last_blocked_at=now,
                    cooldown_until=cooldown_time,
                )
            )
        else:
            quota.last_blocked_at = now
            quota.cooldown_until = cooldown_time

        self.session.flush()
        self.session.commit()

    def refresh_quota_wait(self, artifact_type: ArtifactType | None = None, force: bool = False) -> int:
        """Reset jobs in QUOTA_WAIT state back to PENDING when cooldown has passed or forced.

        Args:
            artifact_type: Specific artifact type to reset, or None for all eligible.
            force: When True, reset matching jobs even if cooldown has not expired yet.

        Returns:
            Number of jobs awakened back to PENDING.
        """
        now = utc_now()
        stmt = select(ArtifactJobRecord).where(ArtifactJobRecord.status == JobStatus.QUOTA_WAIT.value)
        if artifact_type is not None:
            stmt = stmt.where(ArtifactJobRecord.artifact_type == artifact_type.value)
        elif not force:
            stmt = stmt.where(ArtifactJobRecord.cooldown_until <= now)

        records = self.session.scalars(stmt).all()
        for r in records:
            r.status = JobStatus.PENDING.value
            r.cooldown_until = None
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
        return [to_domain_job(r) for r in self.session.scalars(stmt)]

    def get_job(self, job_id: str) -> ArtifactJob | None:
        """Retrieve a specific job by its ID.

        Args:
            job_id: Task UUID.

        Returns:
            Domain ArtifactJob entity or None.
        """
        record = self.session.get(ArtifactJobRecord, job_id)
        return to_domain_job(record) if record else None

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
        record.cooldown_until = None
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

    def count_by_status(
        self, course_code: str | None = None, runnable_only: bool = False
    ) -> dict[JobStatus, int]:
        """Compute the breakdown of jobs across all statuses.

        Args:
            course_code: Optional course filter.
            runnable_only: Leave out paused courses (used to decide when a run is finished).

        Returns:
            Mapping from JobStatus to integer count.
        """
        stmt = select(ArtifactJobRecord.status, func.count(ArtifactJobRecord.id))
        if course_code:
            stmt = stmt.where(ArtifactJobRecord.course_code == course_code)
        if runnable_only:
            paused = select(CourseRecord.code).where(CourseRecord.paused.is_(True))
            stmt = stmt.where(ArtifactJobRecord.course_code.not_in(paused))
        stmt = stmt.group_by(ArtifactJobRecord.status)
        counts = {status: 0 for status in JobStatus}
        for status_str, count in self.session.execute(stmt):
            try:
                counts[JobStatus(status_str)] = count
            except ValueError:
                pass
        return counts

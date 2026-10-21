"""Domain repository protocols: abstract interfaces decoupling services from storage adapters."""

from __future__ import annotations

from typing import Protocol

from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    JobStatus,
)


class QueueRepositoryProtocol(Protocol):
    """Abstract interface for task queue persistence and state transitions."""

    def enqueue_jobs(self, jobs: list[ArtifactJob]) -> int:
        """Enqueue new artifact jobs.

        Args:
            jobs: List of domain ArtifactJob entities to enqueue.

        Returns:
            Number of newly added jobs.
        """
        ...

    def claim_next_job(
        self, worker_id: str, excluded_types: set[ArtifactType] | None = None
    ) -> ArtifactJob | None:
        """Claim the next eligible job atomically.

        Args:
            worker_id: Identifier of the worker claiming the job.
            excluded_types: Artifact types that are currently blocked by quota limits.

        Returns:
            The claimed domain ArtifactJob, or None if no eligible job is waiting.
        """
        ...

    def complete_job(self, job_id: str, output_file: str) -> None:
        """Mark a job as finished.

        Args:
            job_id: Task UUID.
            output_file: Path of the generated output file.
        """
        ...

    def fail_job(self, job_id: str, error_message: str, max_attempts: int = 3) -> None:
        """Record job execution failure.

        Args:
            job_id: Task UUID.
            error_message: Detailed failure explanation.
            max_attempts: Maximum retry threshold before permanent failure.
        """
        ...

    def block_job_quota(self, job_id: str, artifact_type: ArtifactType, cooldown_seconds: int = 3600) -> None:
        """Transition job into quota wait state.

        Args:
            job_id: Task UUID.
            artifact_type: The artifact type that hit quota.
            cooldown_seconds: Duration before quota probe should attempt wake up.
        """
        ...

    def refresh_quota_wait(self, artifact_type: ArtifactType | None = None) -> int:
        """Wake quota-waiting jobs whose cooldown has elapsed.

        Args:
            artifact_type: Specific artifact type to reset, or None for all eligible.

        Returns:
            Number of jobs awakened back to PENDING.
        """
        ...

    def list_jobs(self, course_code: str | None = None, status: JobStatus | None = None) -> list[ArtifactJob]:
        """List tasks matching filters.

        Args:
            course_code: Filter by course identifier.
            status: Filter by job state.

        Returns:
            List of matching domain ArtifactJob entities.
        """
        ...

    def get_job(self, job_id: str) -> ArtifactJob | None:
        """Retrieve a specific job by ID.

        Args:
            job_id: Task UUID.

        Returns:
            Domain ArtifactJob entity or None.
        """
        ...

    def count_by_status(self, course_code: str | None = None) -> dict[JobStatus, int]:
        """Get summary count per status.

        Args:
            course_code: Optional course filter.

        Returns:
            Mapping from JobStatus to integer count.
        """
        ...


class CourseRepositoryProtocol(Protocol):
    """Abstract interface for course and lecture storage."""

    def save_course(self, course: Course) -> None:
        """Persist or update course details.

        Args:
            course: Domain course entity to persist.
        """
        ...

    def get_course(self, code: str) -> Course | None:
        """Retrieve course by code.

        Args:
            code: The unique course code (e.g. BIO101).

        Returns:
            The domain Course entity, or None if not found.
        """
        ...

    def list_courses(self) -> list[Course]:
        """List all courses.

        Returns:
            List of domain Course entities.
        """
        ...

    def update_notebook_id(self, code: str, notebook_id: str) -> None:
        """Update linked NotebookLM notebook ID.

        Args:
            code: Course code.
            notebook_id: Google NotebookLM notebook ID.
        """
        ...

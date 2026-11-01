"""Domain repository protocols: abstract interfaces decoupling services from storage adapters.

`NotebookLMClientProtocol` lives in `notebooklm_protocol.py` and is re-exported here.
"""

from __future__ import annotations

from typing import Protocol

from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    GenerationOptions,
    JobStatus,
    QuizAttempt,
    QuizMistake,
)
from notebooklm_batch_studio.domain.notebooklm_protocol import NotebookLMClientProtocol


class OllamaClientProtocol(Protocol):
    """Abstract interface for local Ollama text generation."""

    def is_available(self) -> bool:
        """Check whether Ollama endpoint is reachable.

        Returns:
            True if service is ready, False otherwise.
        """
        ...

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate text completion from model.

        Args:
            prompt: User prompt content.
            system_prompt: Optional system prompt context.

        Returns:
            Generated text response.
        """
        ...


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

    def complete_job(self, job_id: str, output_file: str, interactive_path: str | None = None) -> None:
        """Mark a job as finished.

        Args:
            job_id: Task UUID.
            output_file: Path of the generated output file.
            interactive_path: Optional path to interactive HTML output.
        """
        ...

    def update_job_style_options(self, job_id: str, style_options: str | None) -> None:
        """Store one job's own option overrides (JSON), or clear them with None.

        Args:
            job_id: Task UUID.
            style_options: JSON object text, or None.
        """
        ...

    def record_artifact_ids(self, job_id: str, artifact_ids: list[str]) -> None:
        """Remember which NotebookLM artifacts / notes a job produced.

        Args:
            job_id: Task UUID.
            artifact_ids: Artifact or note ids.
        """
        ...

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
            artifact_types: Artifact type values.
            from_statuses: Statuses that may change.
            to_status: New status.

        Returns:
            Number of jobs changed.
        """
        ...

    def max_version(self, course_code: str, lecture_no: int | None, artifact_type: ArtifactType) -> int:
        """Return the highest version generated so far for one artifact slot.

        Args:
            course_code: Course code.
            lecture_no: Lecture number, or None for course-wide artifacts.
            artifact_type: Artifact type.

        Returns:
            Highest version, or 0 when none exists.
        """
        ...

    def mark_needs_review(self, job_id: str, output_file: str, message: str) -> None:
        """Mark a job as finished but needing manual review (no automatic retry).

        Args:
            job_id: Task UUID.
            output_file: Path of the quarantined output file.
            message: Why the output needs review.
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

    def retry_job(self, job_id: str) -> bool:
        """Reset a job back to PENDING status to allow re-execution.

        Args:
            job_id: Task UUID.

        Returns:
            True if the job was found and reset, False otherwise.
        """
        ...

    def update_job_prompt(self, job_id: str, prompt: str) -> bool:
        """Update the custom generation prompt for a specific job.

        Args:
            job_id: Task UUID.
            prompt: New custom prompt string.

        Returns:
            True if job was found and updated, False otherwise.
        """
        ...

    def count_by_status(
        self, course_code: str | None = None, runnable_only: bool = False
    ) -> dict[JobStatus, int]:
        """Get summary count per status.

        Args:
            course_code: Optional course filter.
            runnable_only: Leave out paused courses.

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

    def update_artifact_selection(self, code: str, chapter: list[str], whole: list[str]) -> None:
        """Replace a course's chosen per-lecture and course-wide artifact types.

        Args:
            code: Course code.
            chapter: Per-lecture artifact type values.
            whole: Course-wide artifact type values.
        """
        ...

    def delete_course(self, code: str) -> int:
        """Delete a course and its local records (NotebookLM untouched).

        Args:
            code: Course code.

        Returns:
            Number of jobs removed.
        """
        ...

    def set_course_paused(self, code: str, paused: bool) -> None:
        """Pause or resume one course in the queue.

        Args:
            code: Course code.
            paused: True to hold its jobs.
        """
        ...

    def update_course_basics(self, code: str, language: str, mock_exam_questions: int) -> None:
        """Change a course's output language and mock exam question target.

        Args:
            code: Course code.
            language: Output language.
            mock_exam_questions: Mock exam question target.
        """
        ...

    def update_generation_options(self, code: str, options: GenerationOptions) -> None:
        """Store a course's NotebookLM generation options.

        Args:
            code: Course code.
            options: Options to persist.
        """
        ...

    def update_notebook_id(self, code: str, notebook_id: str) -> None:
        """Update linked NotebookLM notebook ID.

        Args:
            code: Course code.
            notebook_id: Google NotebookLM notebook ID.
        """
        ...

    def update_lecture_source_id(self, code: str, lecture_no: int, source_id: str) -> None:
        """Update the NotebookLM source ID for a lecture.

        Args:
            code: Course code.
            lecture_no: Sequence number of the lecture.
            source_id: Uploaded source ID from NotebookLM.
        """
        ...

    def update_profile(self, code: str, profile: str) -> None:
        """Update the artifact generation profile for a course.

        Args:
            code: Course code.
            profile: New profile name (e.g. 'full', 'quiz-only', 'exam-prep').
        """
        ...

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
        ...


class StudyRepositoryProtocol(Protocol):
    """Abstract interface for student study progress, quiz submissions, and mistake tracking."""

    def record_attempt(self, attempt: QuizAttempt) -> None:
        """Persist a completed quiz attempt along with any mistake records.

        Args:
            attempt: Domain QuizAttempt entity containing mistakes.
        """
        ...

    def list_attempts(self, course_code: str, lecture_no: int | None = None) -> list[QuizAttempt]:
        """List quiz attempts for a course or lecture.

        Args:
            course_code: Course code.
            lecture_no: Optional lecture number filter.

        Returns:
            List of domain QuizAttempt entities.
        """
        ...

    def list_mistakes(
        self,
        course_code: str,
        lecture_no: int | None = None,
        only_unresolved: bool = True,
    ) -> list[QuizMistake]:
        """List recorded mistakes for a course or lecture.

        Args:
            course_code: Course code.
            lecture_no: Optional lecture number filter.
            only_unresolved: Whether to include only unresolved mistakes.

        Returns:
            List of domain QuizMistake entities.
        """
        ...

    def resolve_mistake(self, mistake_id: str) -> bool:
        """Mark a quiz mistake as resolved.

        Args:
            mistake_id: UUID of the mistake record.

        Returns:
            True if updated, False if not found.
        """
        ...


__all__ = [
    "CourseRepositoryProtocol",
    "NotebookLMClientProtocol",
    "OllamaClientProtocol",
    "QueueRepositoryProtocol",
    "StudyRepositoryProtocol",
]

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

    def retry_job(self, job_id: str) -> bool:
        """Reset a job back to PENDING status to allow re-execution.

        Args:
            job_id: Task UUID.

        Returns:
            True if the job was found and reset, False otherwise.
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


class NotebookLMClientProtocol(Protocol):
    """Abstract interface for Google NotebookLM operations and artifact generation."""

    def check_auth(self) -> bool:
        """Check whether local authentication session is valid.

        Returns:
            True if session is valid and active, False otherwise.
        """
        ...

    async def create_notebook(self, title: str) -> str:
        """Create a new notebook in NotebookLM.

        Args:
            title: The title of the new notebook.

        Returns:
            The created notebook identifier string.
        """
        ...

    async def upload_source(self, notebook_id: str, file_path: str) -> str:
        """Upload a PDF source file to a notebook.

        Args:
            notebook_id: The notebook identifier.
            file_path: Filesystem path to the local PDF file.

        Returns:
            The uploaded source identifier string.
        """
        ...

    async def wait_source_ready(self, notebook_id: str, source_id: str, timeout_seconds: int = 180) -> None:
        """Wait until an uploaded source is fully indexed and ready for generation.

        Args:
            notebook_id: The notebook identifier.
            source_id: The source identifier.
            timeout_seconds: Maximum time to wait in seconds.
        """
        ...

    async def generate_quiz(self, notebook_id: str, source_ids: list[str], prompt: str | None = None) -> str:
        """Request generation of a quiz from selected sources.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for the quiz generation.

        Returns:
            Task identifier or artifact identifier for the quiz.
        """
        ...

    async def download_quiz(self, notebook_id: str, output_path: str) -> None:
        """Download generated quiz JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
        """
        ...

    async def generate_flashcards(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None
    ) -> str:
        """Request generation of flashcards from selected sources.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for flashcards generation.

        Returns:
            Task identifier or artifact identifier for the flashcards.
        """
        ...

    async def download_flashcards(self, notebook_id: str, output_path: str) -> None:
        """Download generated flashcards JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
        """
        ...

    async def generate_mind_map(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None
    ) -> str:
        """Request generation of a mind map from selected sources.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for mind map generation.

        Returns:
            Task identifier or artifact identifier for the mind map.
        """
        ...

    async def download_mind_map(self, notebook_id: str, output_path: str) -> None:
        """Download generated mind map JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
        """
        ...

    async def generate_audio(self, notebook_id: str, source_ids: list[str], prompt: str | None = None) -> str:
        """Request generation of Deep Dive Audio overview.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional customization prompt for audio discussion.

        Returns:
            Task identifier or status string for audio generation.
        """
        ...

    async def download_audio(self, notebook_id: str, output_path: str) -> None:
        """Download generated Audio MP3 file to local storage.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where MP3 should be saved.
        """
        ...

    async def rename_artifact(self, notebook_id: str, artifact_id: str, title: str) -> None:
        """Rename an artifact within NotebookLM for readability.

        Args:
            notebook_id: The notebook identifier.
            artifact_id: The artifact identifier to rename.
            title: The new title string (e.g. '[03] Quiz 1-基礎').
        """
        ...

"""Domain repository protocols: abstract interfaces decoupling services from storage adapters."""

from __future__ import annotations

from typing import Any, Protocol

from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    GenerationOptions,
    JobStatus,
    QuizAttempt,
    QuizMistake,
)


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

    def update_artifact_selection(self, code: str, chapter: list[str], whole: list[str]) -> None:
        """Replace a course's chosen per-lecture and course-wide artifact types.

        Args:
            code: Course code.
            chapter: Per-lecture artifact type values.
            whole: Course-wide artifact type values.
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


class NotebookLMClientProtocol(Protocol):
    """Abstract interface for Google NotebookLM operations and artifact generation.

    Every `generate_*` waits for completion and returns the artifact id; callers pass that id
    to the matching `download_*` and to `rename_artifact`. Refs: ADR-004
    """

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

    async def get_source_limit(self) -> int | None:
        """Return the maximum number of sources allowed per notebook.

        Returns:
            Source limit, or None when unknown.
        """
        ...

    async def get_quota_status(self) -> dict[str, Any]:
        """Return the live usage meter and account limits.

        Returns:
            JSON-friendly quota summary.
        """
        ...

    async def generate_quiz(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        difficulty: str | None = None,
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate a quiz from selected sources and wait for completion.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for the quiz generation.
            difficulty: 'easy', 'medium', 'hard', or None for the default.
            options: Course generation options (None = defaults).

        Returns:
            The completed quiz artifact id.
        """
        ...

    async def download_quiz(self, notebook_id: str, output_path: str, artifact_id: str | None = None) -> None:
        """Download generated quiz JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_flashcards(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        options: GenerationOptions | None = None,
    ) -> str:
        """Request generation of flashcards from selected sources.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for flashcards generation.
            options: Course generation options (None = defaults).

        Returns:
            The completed flashcards artifact id.
        """
        ...

    async def download_flashcards(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download generated flashcards JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_mind_map(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Generate a mind map from selected sources.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for mind map generation.
            language: Course language ('zh-TW', 'en', 'bilingual').

        Returns:
            The mind map note id (pass it to download_mind_map).
        """
        ...

    async def download_mind_map(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download generated mind map JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_audio(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate a Deep Dive audio overview and wait for completion.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional customization prompt for audio discussion.
            language: Course language ('zh-TW', 'en', 'bilingual').
            options: Course generation options (None = defaults).

        Returns:
            The completed audio artifact id.
        """
        ...

    async def download_audio(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download generated Audio MP3 file to local storage.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where MP3 should be saved.
            artifact_id: Optional artifact identifier.
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

    async def rename_mind_map(self, notebook_id: str, note_id: str, title: str) -> None:
        """Rename a note-backed mind map within NotebookLM. Refs: ISSUE-011

        Args:
            notebook_id: The notebook identifier.
            note_id: The mind map note identifier.
            title: The new title string.
        """
        ...

    async def generate_report(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        report_format: str = "briefing_doc",
    ) -> str:
        """Request generation of a study guide or briefing report.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language ('zh-TW', 'en', 'bilingual').
            report_format: Format key (briefing_doc, study_guide, blog_post).

        Returns:
            Task or artifact identifier.
        """
        ...

    async def download_report(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download report/study guide content to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_slide_deck(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Request generation of slide deck presentation outline.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.
            options: Course generation options (None = defaults).

        Returns:
            Task or artifact identifier.
        """
        ...

    async def download_slide_deck(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None, output_format: str = "pdf"
    ) -> None:
        """Download a slide deck as PDF or PPTX.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
            output_format: 'pdf' or 'pptx'.
        """
        ...

    async def generate_infographic(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Request generation of an infographic.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.
            options: Course generation options (None = defaults).

        Returns:
            Task or artifact identifier.
        """
        ...

    async def download_infographic(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download infographic to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_data_table(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Request generation of comparison data table.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.

        Returns:
            Task or artifact identifier.
        """
        ...

    async def download_data_table(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download data table content to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_video(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Request generation of cinematic video overview.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.
            options: Course generation options (None = defaults).

        Returns:
            Task or artifact identifier.
        """
        ...

    async def download_video(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download generated video to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def list_artifacts(self, notebook_id: str) -> list[dict[str, Any]]:
        """List all remote artifacts present in a notebook.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            List of dictionary summaries of artifacts.
        """
        ...

    async def download_artifact_by_kind(
        self, notebook_id: str, artifact_id: str, kind: str, output_path: str
    ) -> str:
        """Download remote artifact using the method matching its kind.

        Args:
            notebook_id: Notebook identifier.
            artifact_id: Artifact identifier.
            kind: Artifact kind string.
            output_path: Target path.

        Returns:
            Target output path string.
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

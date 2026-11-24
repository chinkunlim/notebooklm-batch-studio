"""Batch orchestrator: coordinates course scanning, task enqueuing, and execution.

Integrates CourseRepository, QueueRepository, Gemini Notebook client, artifact converters,
and the parallel WorkerPool to provide an end-to-end processing pipeline.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import (
    CourseNotFoundError,
    OllamaUnavailableError,
)
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    Course,
    JobStatus,
    ProfileName,
)
from notebooklm_batch_studio.domain.repositories import (
    CourseRepositoryProtocol,
    NotebookLMClientProtocol,
    OllamaClientProtocol,
    QueueRepositoryProtocol,
)
from notebooklm_batch_studio.domain.study_hierarchy import resolve_course_output_root
from notebooklm_batch_studio.services.artifact_runner import ArtifactRunner, JobTarget
from notebooklm_batch_studio.services.course_onboarding import CourseOnboardingMixin
from notebooklm_batch_studio.services.course_settings import CourseSettingsService, apply_job_settings
from notebooklm_batch_studio.services.prompt_generator import PromptGenerator
from notebooklm_batch_studio.services.quiz_reader import read_quiz_content
from notebooklm_batch_studio.services.quota_planner import ensure_quota_for
from notebooklm_batch_studio.services.reporter import CourseReporter
from notebooklm_batch_studio.services.source_manager import CourseSourceMixin
from notebooklm_batch_studio.services.sync_service import RemoteSyncService
from notebooklm_batch_studio.services.worker_pool import (
    QueueSessionProvider,
    WorkerPool,
    generate_jobs_for_course,
)

logger = logging.getLogger(__name__)


class BatchStudioService(CourseOnboardingMixin, CourseSourceMixin):
    """Core domain service for orchestrating course batch operations."""

    def __init__(
        self,
        course_repo: CourseRepositoryProtocol,
        queue_repo: QueueRepositoryProtocol,
        *args: Any,
        **options: Any,
    ) -> None:
        """Initialize the batch studio service.

        Args:
            course_repo: Repository for course and lecture persistence.
            queue_repo: Repository for task queue state.
            *args: Optional positional `notebooklm_client` and `config`.
            **options: Optional `notebooklm_client`, `config`, `queue_provider`, and `ollama_client`.
        """
        notebooklm_client: NotebookLMClientProtocol = (
            args[0] if len(args) >= 1 else options["notebooklm_client"]
        )
        raw_config: AppConfig = args[1] if len(args) >= 2 else options["config"]
        queue_provider: QueueSessionProvider | None = options.get("queue_provider")
        ollama_client: OllamaClientProtocol | None = options.get("ollama_client")

        self.course_repo = course_repo
        self.queue_repo = queue_repo
        self.notebooklm_client = notebooklm_client
        self.config = raw_config
        self.reporter = CourseReporter(self.config.courses_output_dir)
        self.runner = ArtifactRunner(self.notebooklm_client, self.config)
        self.queue_provider: QueueSessionProvider = queue_provider or self._default_queue_provider
        self.ollama_client = ollama_client
        self.worker_pool: WorkerPool | None = None
        self._is_queue_running = False
        self.course_settings = CourseSettingsService(course_repo, queue_repo, self.config)

    @contextmanager
    def _default_queue_provider(self) -> Iterator[QueueRepositoryProtocol]:
        """Default fallback queue provider yielding the bound queue repository.

        Yields:
            The bound QueueRepositoryProtocol instance.
        """
        yield self.queue_repo

    async def get_notebooklm_quota(self) -> dict[str, Any]:
        """Return the live Gemini Notebook usage meter and account limits.

        Returns:
            Quota summary from the Gemini Notebook adapter.
        """
        return await self.notebooklm_client.get_quota_status()

    def enqueue_course_artifacts(self, course_code: str) -> int:
        """Generate artifact jobs based on active profile and enqueue into database.

        Args:
            course_code: Course code identifier.

        Returns:
            Count of newly added tasks in queue.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")

        jobs = generate_jobs_for_course(course)
        added = self.queue_repo.enqueue_jobs(jobs)
        logger.info("Enqueued %d jobs for course %s", added, course_code)
        return added

    def _resolve_job_target(
        self, job: ArtifactJob, course: Course, nb_id: str
    ) -> tuple[ArtifactJob, Course, JobTarget]:
        """Apply job overrides and resolve source ids and output directory.

        Args:
            job: Claimed artifact job entity.
            course: Associated domain Course entity.
            nb_id: Resolved Gemini Notebook notebook identifier.

        Returns:
            Tuple of (configured_job, narrowed_course, JobTarget).
        """
        run_job, run_course = apply_job_settings(job, course)  # SPEC-006 (may narrow lectures)
        course_out_root = resolve_course_output_root(
            self.config.courses_output_dir, course.code, course.study_dir
        )
        if job.lecture_no is not None:
            lec = next((item for item in course.lectures if item.no == job.lecture_no), None)
            source_ids = [lec.source_id] if (lec and lec.source_id) else []
            lec_dir_name = f"{job.lecture_no:02d}_{lec.topic if lec else 'lecture'}"
            out_dir = course_out_root / lec_dir_name
        else:
            source_ids = [item.source_id for item in run_course.lectures if item.source_id]
            out_dir = course_out_root / "_course_synthesis"

        out_dir.mkdir(parents=True, exist_ok=True)
        return run_job, run_course, JobTarget(nb_id=nb_id, source_ids=source_ids, out_dir=out_dir)

    async def execute_job(self, job: ArtifactJob) -> str:
        """Process a single artifact generation task from the queue.

        Args:
            job: The claimed ArtifactJob entity.

        Returns:
            Output file path or review folder path upon completion.

        Raises:
            CourseNotFoundError: When the job's course is missing.
            QuotaExceededError: When the live meter says this action has no quota left.
        """
        course = self.course_repo.get_course(job.course_code)
        if course is None:
            raise CourseNotFoundError(f"Course {job.course_code} not found")
        await ensure_quota_for(self.notebooklm_client, job.artifact_type)
        if not course.notebook_id or any(
            not lec.source_id or lec.upload_status == "failed" for lec in course.lectures
        ):
            logger.info("Initializing Gemini Notebook notebook and sources for course %s", course.code)
            course = await self.setup_notebook_and_sources(course.code)

        nb_id = course.notebook_id
        if not nb_id:
            raise RuntimeError(f"Course {job.course_code} lacks Gemini Notebook notebook_id")

        run_job, run_course, target = self._resolve_job_target(job, course, nb_id)
        path, artifact_ids = await self.runner.process_job_with_ids(run_job, run_course, target)
        with self.queue_provider() as repo:
            repo.record_artifact_ids(job.id, artifact_ids)  # Refs: ADR-005
        return path

    def generate_summary(self, course_code: str) -> tuple[Path, Path]:
        """Generate summary.md and summary.html for a given course.

        Args:
            course_code: Course identifier.

        Returns:
            Tuple of (summary_md_path, summary_html_path).
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")

        jobs = self.queue_repo.list_jobs(course_code=course_code)
        status_map: dict[tuple[int | None, str], JobStatus] = {
            (j.lecture_no, j.artifact_type.value): j.status for j in jobs
        }
        return self.reporter.generate_summary(course, status_map)

    def get_quiz_content(
        self, course_code: str, lecture_no: int, variant: str, with_answers: bool = False
    ) -> dict[str, Any]:
        """Locate and read generated quiz content for a specific lecture.

        Args:
            course_code: Course code identifier.
            lecture_no: Sequence number of the lecture.
            variant: Quiz variant ('1-基礎', '2-理解', '3-模擬考', 'quiz_1', 'quiz_2', 'quiz_3').
            with_answers: If False, returns questions-only markdown; if True, includes answer key.

        Returns:
            Dictionary containing quiz metadata, question count, and content text.

        Raises:
            CourseNotFoundError: If course does not exist.
            FileNotFoundError: If the quiz files have not yet been produced.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")

        return read_quiz_content(
            self.config.courses_output_dir, course, lecture_no, variant=variant, with_answers=with_answers
        )

    def retry_job(self, job_id: str) -> bool:
        """Reset a failed, needs-review, or quota-waiting task back to pending and ensure queue starts.

        Args:
            job_id: Task UUID.

        Returns:
            True if task was reset, False if job not found.
        """
        job = self.queue_repo.get_job(job_id)
        ok = self.queue_repo.retry_job(job_id)
        if ok:
            if job is not None and self.worker_pool is not None:
                self.worker_pool.blocked_quota_types.discard(job.artifact_type)
            self.start_queue()
        return ok

    def retry_course_failed_jobs(
        self, course_code: str | None = None, include_needs_review: bool = True
    ) -> int:
        """Reset failed (and optionally needs_review) jobs to pending and start the worker pool.

        Args:
            course_code: Optional course filter (validated when supplied).
            include_needs_review: Also reset NEEDS_REVIEW jobs back to pending.

        Returns:
            Number of jobs re-queued to pending.

        Raises:
            CourseNotFoundError: When `course_code` does not exist.
        """
        if course_code is not None and self.course_repo.get_course(course_code) is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")
        count = self.queue_repo.retry_failed_jobs(
            course_code=course_code, include_needs_review=include_needs_review, respect_cooldown=False
        )
        if self.worker_pool is not None:
            self.worker_pool.blocked_quota_types.clear()
        self.start_queue()
        logger.info("Re-queued %d failed job(s) for course=%s", count, course_code or "*")
        return int(count)

    def resume_quota_wait(self) -> int:
        """Wake all quota-blocked and failed tasks back to pending immediately.

        Returns:
            Number of awakened jobs.
        """
        awakened = self.queue_repo.refresh_quota_wait(force=True)
        retried = self.queue_repo.retry_failed_jobs(include_needs_review=False, respect_cooldown=False)
        if isinstance(retried, int):
            awakened += retried
        if self.worker_pool is not None:
            self.worker_pool.blocked_quota_types.clear()
        return awakened

    def set_course_profile(self, course_code: str, profile: str) -> dict[str, Any]:
        """Update active profile for a course and enqueue missing jobs.

        Args:
            course_code: Course identifier.
            profile: New profile name.

        Returns:
            Updated course summary.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")

        prof_enum = ProfileName(profile)
        self.course_repo.update_profile(course_code, prof_enum.value)
        course = dataclasses.replace(course, profile=prof_enum)
        new_jobs = generate_jobs_for_course(course)
        enqueued = self.queue_repo.enqueue_jobs(new_jobs)
        return {
            "course_code": course_code,
            "profile": prof_enum.value,
            "new_jobs_enqueued": enqueued,
        }

    def check_auth_status(self) -> dict[str, Any]:
        """Check Gemini Notebook credential readiness.

        Returns:
            Dictionary indicating whether login state file is valid.
        """
        storage_path = str(self.config.notebooklm_home / "profiles" / "default" / "storage_state.json")
        has_auth = False
        if hasattr(self.notebooklm_client, "check_auth"):
            has_auth = bool(self.notebooklm_client.check_auth())
        else:
            has_auth = Path(storage_path).exists()
        return {"authenticated": has_auth, "storage_path": storage_path}

    def is_queue_running(self) -> bool:
        """Check if queue execution is currently active.

        Returns:
            True if running and not paused, False otherwise.
        """
        if self.worker_pool is not None:
            return self.worker_pool._running and not self.worker_pool.is_paused
        return self._is_queue_running

    def pause_queue(self) -> bool:
        """Pause active queue processing gracefully.

        Returns:
            True upon pause request.
        """
        self._is_queue_running = False
        if self.worker_pool:
            self.worker_pool.pause()
            logger.info("WorkerPool paused gracefully.")
        return True

    def resume_queue(self) -> bool:
        """Resume active queue processing.

        Returns:
            True upon resume request.
        """
        self._is_queue_running = True
        if self.worker_pool:
            self.worker_pool.resume()
            logger.info("WorkerPool resumed.")
        else:
            self.start_queue()
        return True

    def _schedule_worker_pool_start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Ensure a WorkerPool exists and schedule its startup task on an active loop.

        Args:
            loop: Running asyncio event loop.
        """
        if loop.is_closed():
            return
        if self.worker_pool is None:
            self.worker_pool = WorkerPool(
                queue_provider=self.queue_provider, executor=self.execute_job, concurrency=2
            )
        if not self.worker_pool._running:
            loop.create_task(self.worker_pool.start())
            logger.info("WorkerPool background start scheduled.")

    def start_queue(self) -> bool:
        """Re-queue any FAILED jobs and start active queue processing.

        Returns:
            True upon start request.
        """
        retry_fn = getattr(self.queue_repo, "retry_failed_jobs", None)
        if callable(retry_fn):
            retry_fn(include_needs_review=False, respect_cooldown=False)
        self._is_queue_running = True
        if self.worker_pool and self.worker_pool.is_paused:
            self.worker_pool.resume()
            return True

        try:
            self._schedule_worker_pool_start(asyncio.get_running_loop())
        except RuntimeError:
            pass
        return True

    def update_job_prompt(self, job_id: str, prompt: str) -> bool:
        """Update customized prompt for an artifact generation job.

        Args:
            job_id: Task UUID.
            prompt: Customized prompt string.

        Returns:
            True if updated, False otherwise.
        """
        return self.queue_repo.update_job_prompt(job_id, prompt)

    def refine_course_prompts_with_ollama(self, course_code: str) -> int:
        """Rewrite prompts of a course's unfinished jobs using local Ollama.

        DONE and RUNNING jobs are skipped; only prompts that actually changed are counted.
        Refs: ISSUE-001

        Args:
            course_code: Course identifier.

        Returns:
            Count of prompts that were replaced by an Ollama-refined version.

        Raises:
            CourseNotFoundError: If the course does not exist.
            OllamaUnavailableError: If no Ollama client is configured or it is unreachable.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")
        if self.ollama_client is None or not self.ollama_client.is_available():
            raise OllamaUnavailableError(
                "Ollama is not configured or not reachable; prompts were not changed"
            )

        prompt_gen = PromptGenerator(self.ollama_client)
        skip = (JobStatus.DONE, JobStatus.RUNNING)
        jobs = [j for j in self.queue_repo.list_jobs(course_code=course_code) if j.status not in skip]
        updated_count = 0
        for j in jobs:
            lec = next((item for item in course.lectures if item.no == j.lecture_no), None)
            topic = lec.topic if lec else "全範圍整合"
            base = prompt_gen.get_base_blueprint_prompt(j.artifact_type, topic, course.name, course.language)
            refined = prompt_gen.generate_refined_prompt(
                j.artifact_type, topic, course.name, language=course.language, use_ollama=True
            )
            if refined and refined != base and self.queue_repo.update_job_prompt(j.id, refined):
                updated_count += 1
        logger.info("Refined %d/%d prompts with Ollama for course %s", updated_count, len(jobs), course_code)
        return updated_count

    def _sync_service(self) -> RemoteSyncService:
        """Build a RemoteSyncService bound to current repos and output dir."""
        return RemoteSyncService(
            notebooklm_client=self.notebooklm_client,
            course_repo=self.course_repo,
            queue_repo=self.queue_repo,
            output_base_dir=self.config.output_dir,
        )

    async def sync_course_artifacts(self, course_code: str) -> dict[str, Any]:
        """Synchronize remote Gemini Notebook artifacts back to local storage and database.

        Args:
            course_code: Course identifier.

        Returns:
            Dictionary summary with count and synced item metadata.
        """
        return await self._sync_service().sync_course(course_code)

    async def list_remote_artifacts(self, course_code: str) -> dict[str, Any]:
        """List remote Gemini Notebook artifacts annotated with active local version info.

        Args:
            course_code: Course identifier.

        Returns:
            Dictionary with course metadata and annotated remote artifacts.
        """
        return await self._sync_service().list_remote_artifacts(course_code)

    async def delete_remote_artifact(
        self, course_code: str, artifact_id: str, delete_local: bool = False
    ) -> dict[str, Any]:
        """Delete a remote Gemini Notebook artifact and unlink/clean local job state.

        Args:
            course_code: Course identifier.
            artifact_id: Remote artifact identifier.
            delete_local: Whether to also delete the downloaded local file.

        Returns:
            Deletion summary dictionary.
        """
        return await self._sync_service().delete_remote_artifact(
            course_code, artifact_id, delete_local=delete_local
        )

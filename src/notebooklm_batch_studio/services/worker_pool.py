"""Parallel worker pool: manages concurrent task execution, quota isolation, and auto-resume."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Awaitable, Callable, ContextManager

from notebooklm_batch_studio.domain.exceptions import QuotaExceededError
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    JobStatus,
    ProfileName,
)
from notebooklm_batch_studio.domain.repositories import QueueRepositoryProtocol
from notebooklm_batch_studio.services.prompt_generator import PromptGenerator

logger = logging.getLogger(__name__)


def _get_types_for_profile(profile: ProfileName) -> list[ArtifactType]:
    """Return the list of artifact types required for a single lecture under the given profile.

    Args:
        profile: Selected generation profile.

    Returns:
        List of ArtifactType enum values.
    """
    if profile == ProfileName.FULL:
        return [
            ArtifactType.AUDIO,
            ArtifactType.QUIZ_1,
            ArtifactType.QUIZ_2,
            ArtifactType.QUIZ_3,
            ArtifactType.INFOGRAPHIC,
            ArtifactType.MIND_MAP,
            ArtifactType.FLASHCARDS,
            ArtifactType.STUDY_GUIDE,
        ]
    if profile == ProfileName.QUIZ_ONLY:
        return [
            ArtifactType.QUIZ_1,
            ArtifactType.QUIZ_2,
            ArtifactType.QUIZ_3,
            ArtifactType.FLASHCARDS,
        ]
    if profile == ProfileName.EXAM_PREP:
        return [
            ArtifactType.QUIZ_3,
            ArtifactType.STUDY_GUIDE,
        ]
    return []


def _make_job(
    course_code: str,
    lecture_no: int | None,
    art_type: ArtifactType,
    custom_prompt: str | None = None,
) -> ArtifactJob:
    """Create a new pending ArtifactJob with a fresh UUID.

    Args:
        course_code: Course code.
        lecture_no: Sequence number or None for course-level.
        art_type: Artifact type.
        custom_prompt: Optional tailored prompt.

    Returns:
        ArtifactJob domain object.
    """
    return ArtifactJob(
        id=str(uuid.uuid4()),
        course_code=course_code,
        lecture_no=lecture_no,
        artifact_type=art_type,
        status=JobStatus.PENDING,
        custom_prompt=custom_prompt,
    )


def generate_jobs_for_course(course: Course) -> list[ArtifactJob]:
    """Create the matrix of scheduled ArtifactJob entities for a course based on settings.

    Supports custom granular selections (selected_chapter_artifacts, selected_course_artifacts)
    or falls back to legacy predefined profiles.

    Args:
        course: The Course domain entity containing lectures and selected settings.

    Returns:
        List of ready-to-enqueue ArtifactJob objects with unique identifiers.
    """
    jobs: list[ArtifactJob] = []

    prompt_gen = PromptGenerator()
    # If granular custom selection is provided
    if course.selected_chapter_artifacts or course.selected_course_artifacts:
        chapter_types: list[ArtifactType] = []
        for name in course.selected_chapter_artifacts:
            try:
                chapter_types.append(ArtifactType(name))
            except ValueError:
                logger.warning("Unknown chapter artifact type: %s", name)

        course_types: list[ArtifactType] = []
        for name in course.selected_course_artifacts:
            try:
                course_types.append(ArtifactType(name))
            except ValueError:
                logger.warning("Unknown course artifact type: %s", name)

        for lec in course.lectures:
            for art_type in chapter_types:
                p = prompt_gen.get_base_blueprint_prompt(art_type, lec.topic, course.name, course.language)
                jobs.append(_make_job(course.code, lec.no, art_type, custom_prompt=p))

        course_scope = f"{course.code} 全範圍整合"
        for course_art in course_types:
            p = prompt_gen.get_base_blueprint_prompt(course_art, course_scope, course.name, course.language)
            jobs.append(_make_job(course.code, None, course_art, custom_prompt=p))

        logger.info(
            "Generated %d granular jobs for course %s (chapter_types=%d, course_types=%d)",
            len(jobs),
            course.code,
            len(chapter_types),
            len(course_types),
        )
        return jobs

    # Fallback to predefined profile
    types_for_lecture = _get_types_for_profile(course.profile)
    for lec in course.lectures:
        for art_type in types_for_lecture:
            p = prompt_gen.get_base_blueprint_prompt(art_type, lec.topic, course.name, course.language)
            jobs.append(_make_job(course.code, lec.no, art_type, custom_prompt=p))

    if course.profile in (ProfileName.FULL, ProfileName.EXAM_PREP):
        for course_art in (ArtifactType.COURSE_MOCK_EXAM, ArtifactType.COURSE_MIND_MAP):
            p = prompt_gen.get_base_blueprint_prompt(
                course_art, f"{course.code} 全範圍整合", course.name, course.language
            )
            jobs.append(_make_job(course.code, None, course_art, custom_prompt=p))

    logger.info("Generated %d jobs for course %s (profile=%s)", len(jobs), course.code, course.profile.value)
    return jobs


# Type alias for the job executor callback function
JobExecutor = Callable[[ArtifactJob], Awaitable[str]]
QueueSessionProvider = Callable[[], ContextManager[QueueRepositoryProtocol]]


class WorkerPool:
    """Manages 2~3 concurrent workers executing generation tasks with quota isolation."""

    def __init__(
        self,
        queue_provider: QueueSessionProvider,
        executor: JobExecutor,
        concurrency: int = 3,
        probe_interval_seconds: float = 60.0,
    ) -> None:
        """Initialize the parallel worker pool.

        Args:
            queue_provider: Context manager factory providing a QueueRepositoryProtocol.
            executor: Async callback function that performs the actual generation work.
            concurrency: Number of parallel workers (recommended: 2~3).
            probe_interval_seconds: Frequency in seconds to check quota refresh.
        """
        self.queue_provider = queue_provider
        self.executor = executor
        self.concurrency = concurrency
        self.probe_interval_seconds = probe_interval_seconds
        self.blocked_quota_types: set[ArtifactType] = set()
        self._running = False
        self._paused = False
        self._workers: list[asyncio.Task[None]] = []
        self._probe_task: asyncio.Task[None] | None = None

    def pause(self) -> None:
        """Gracefully pause queue: running jobs finish, but no new jobs are claimed."""
        self._paused = True
        logger.info("WorkerPool paused gracefully.")

    def resume(self) -> None:
        """Resume claiming pending jobs from queue."""
        self._paused = False
        logger.info("WorkerPool resumed.")

    @property
    def is_paused(self) -> bool:
        """Whether worker pool is in paused state.

        Returns:
            True if paused, False otherwise.
        """
        return self._paused

    async def start(self) -> None:
        """Launch worker tasks and quota probe scheduler."""
        if self._running:
            return
        self._running = True
        logger.info("Starting WorkerPool with concurrency=%d", self.concurrency)
        for i in range(self.concurrency):
            worker_id = f"worker-{i + 1}"
            task = asyncio.create_task(self._worker_loop(worker_id))
            self._workers.append(task)
        self._probe_task = asyncio.create_task(self._quota_probe_loop())

    async def stop(self) -> None:
        """Gracefully stop all worker tasks."""
        if not self._running:
            return
        logger.info("Stopping WorkerPool...")
        self._running = False
        if self._probe_task:
            self._probe_task.cancel()
        for t in self._workers:
            t.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._probe_task = None
        logger.info("WorkerPool stopped.")

    async def run_until_empty(self, idle_timeout: float = 2.0) -> None:
        """Run workers until no pending or running jobs remain, then stop.

        Args:
            idle_timeout: Seconds to wait after queue becomes empty before shutting down.
        """
        await self.start()
        idle_start: float | None = None
        while self._running:
            await asyncio.sleep(0.5)
            with self.queue_provider() as repo:
                counts = repo.count_by_status()
            pending = counts.get(JobStatus.PENDING, 0)
            running = counts.get(JobStatus.RUNNING, 0)
            if pending == 0 and running == 0:
                if idle_start is None:
                    idle_start = time.time()
                elif time.time() - idle_start >= idle_timeout:
                    break
            else:
                idle_start = None
        await self.stop()

    async def _process_job(self, worker_id: str, job: ArtifactJob) -> None:
        """Execute a single claimed job and record success or failure.

        Args:
            worker_id: The identifier for this worker.
            job: The claimed ArtifactJob entity.
        """
        logger.info("Worker %s processing job=%s (%s)", worker_id, job.id, job.artifact_type.value)
        try:
            output_file = await self.executor(job)
            with self.queue_provider() as repo:
                repo.complete_job(job.id, output_file)
            logger.info("Worker %s completed job=%s output=%s", worker_id, job.id, output_file)

        except QuotaExceededError as q_err:
            logger.warning(
                "Worker %s encountered quota limit for %s: %s",
                worker_id,
                job.artifact_type.value,
                q_err,
            )
            self.blocked_quota_types.add(job.artifact_type)
            with self.queue_provider() as repo:
                repo.block_job_quota(job.id, job.artifact_type, cooldown_seconds=q_err.retry_after_seconds)

        except Exception as err:
            logger.exception("Worker %s failed job=%s: %s", worker_id, job.id, err)
            with self.queue_provider() as repo:
                repo.fail_job(job.id, error_message=str(err))

    async def _worker_loop(self, worker_id: str) -> None:
        """Main execution loop for an individual worker.

        Args:
            worker_id: The identifier for this worker.
        """
        logger.info("Worker %s started", worker_id)
        while self._running:
            if self._paused:
                await asyncio.sleep(0.05)
                continue

            job: ArtifactJob | None = None
            with self.queue_provider() as repo:
                job = repo.claim_next_job(worker_id=worker_id, excluded_types=self.blocked_quota_types)

            if job is None:
                await asyncio.sleep(1.0)
                continue

            await self._process_job(worker_id, job)

    async def _quota_probe_loop(self) -> None:
        """Periodic loop checking if blocked quota types can be refreshed."""
        logger.info("Quota probe scheduler started (interval=%.1fs)", self.probe_interval_seconds)
        while self._running:
            try:
                await asyncio.sleep(self.probe_interval_seconds)
                awakened = 0
                with self.queue_provider() as repo:
                    awakened = repo.refresh_quota_wait()

                if awakened > 0:
                    logger.info("Quota probe awakened %d tasks back to PENDING", awakened)
                    self.blocked_quota_types.clear()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Error during quota probe check: %s", e)

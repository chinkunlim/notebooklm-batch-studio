"""Parallel worker pool: manages concurrent task execution, quota isolation, and auto-resume."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, ContextManager

from notebooklm_batch_studio.domain.exceptions import NeedsReviewError, QuotaExceededError
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, JobStatus
from notebooklm_batch_studio.domain.repositories import QueueRepositoryProtocol
from notebooklm_batch_studio.services.job_planner import (
    generate_jobs_for_course as generate_jobs_for_course,
)

logger = logging.getLogger(__name__)

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
        """Resume claiming pending jobs from queue and clear stale quota blocks."""
        self._paused = False
        self.blocked_quota_types.clear()
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
        with self.queue_provider() as repo:
            recover = getattr(repo, "recover_running_jobs", None)
            recovered = recover() if callable(recover) else 0
        if recovered:
            logger.info("Recovered %d orphaned RUNNING job(s) back to PENDING", recovered)
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

    async def run_until_empty(self, idle_timeout: float = 2.0, wait_for_quota: bool = False) -> None:
        """Run workers until no pending or running jobs remain, then stop.

        Args:
            idle_timeout: Seconds to wait after queue becomes empty before shutting down.
            wait_for_quota: Also keep running while jobs wait in QUOTA_WAIT; the probe loop
                wakes them when their cooldown passes, so the run finishes everything.
        """
        await self.start()
        idle_start: float | None = None
        while self._running:
            await asyncio.sleep(0.5)
            with self.queue_provider() as repo:
                counts = repo.count_by_status(runnable_only=True)
            pending = counts.get(JobStatus.PENDING, 0)
            running = counts.get(JobStatus.RUNNING, 0)
            waiting = counts.get(JobStatus.QUOTA_WAIT, 0) if wait_for_quota else 0
            if pending == 0 and running == 0 and waiting == 0:
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

        except NeedsReviewError as review:  # Refs: ISSUE-002
            logger.warning("Worker %s job=%s needs review: %s", worker_id, job.id, review)
            with self.queue_provider() as repo:
                repo.mark_needs_review(job.id, review.output_file, str(review))

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
            # Brief backoff avoids immediate tight-loop claims on transient failures (ISSUE-038).
            await asyncio.sleep(0.2)

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
                with self.queue_provider() as repo:
                    awakened = repo.refresh_quota_wait()
                    retry_fn = getattr(repo, "retry_failed_jobs", None)
                    retried = retry_fn(respect_cooldown=True) if callable(retry_fn) else 0
                    active_types = {job.artifact_type for job in repo.list_jobs(status=JobStatus.QUOTA_WAIT)}

                if awakened > 0:
                    logger.info("Quota probe awakened %d tasks back to PENDING", awakened)
                if isinstance(retried, int) and retried > 0:
                    logger.info("Probe auto-retried %d failed task(s) back to PENDING", retried)
                stale = self.blocked_quota_types - active_types
                if stale:
                    self.blocked_quota_types.intersection_update(active_types)
                    logger.info("Quota probe pruned cleared quota blocks: %s", sorted(t.value for t in stale))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Error during quota probe check: %s", e)

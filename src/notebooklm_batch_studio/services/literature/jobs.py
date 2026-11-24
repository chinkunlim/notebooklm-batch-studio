"""Single-flight background job runner for literature fetch batches (SPEC-012)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.literature.tracker import AlreadyRunningError, Job, JobState
from notebooklm_batch_studio.services.literature.manager import LiteratureManager, ProcessBatchOptions
from notebooklm_batch_studio.services.literature.protocols import LiteratureRepoProtocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobRunOptions:
    """Options controlling one background literature fetch run.

    Attributes:
        keys: Optional list of item keys; None selects all pending/review items.
        interactive: Enable manual Chrome mode for bot checks / OpenAthens login.
        identify_only: Only resolve metadata and APA 7 without downloading PDFs.
        no_browser: Skip Playwright browser sources.
        on_done: Optional callback invoked when the job finishes.
    """

    keys: list[str] | None = None
    refresh_keys: frozenset[str] = frozenset()
    interactive: bool = False
    identify_only: bool = False
    no_browser: bool = False
    on_done: Callable[[], None] | None = None


@dataclass
class _LiveProgress:
    """In-memory progress snapshot for the currently running literature job."""

    job_id: int
    current_key: str = ""
    stage: str = ""
    done: int = 0
    total: int = 0


class LiteratureJobRunner:
    """Runs at most one background literature fetch job at a time."""

    def __init__(
        self,
        manager_scope: Callable[[], AbstractContextManager[LiteratureManager]],
        lock_path: Path | None = None,
        lock_factory: Callable[[Path], AbstractContextManager[Any]] | None = None,
    ) -> None:
        """Initialize the job runner with a context-managed `LiteratureManager` factory.

        Args:
            manager_scope: Callable returning a context manager that yields `LiteratureManager`.
            lock_path: Optional lock file path; defaults to `config.literature_job_lock_path`.
            lock_factory: Optional cross-process lock factory accepting `Path`.
        """
        self._manager_scope = manager_scope
        self._lock_path = lock_path
        self._lock_factory = lock_factory
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._live: _LiveProgress | None = None
        self._close_stale_on_startup()

    def _build_run_lock(self, manager: LiteratureManager) -> AbstractContextManager[Any] | None:
        """Build the OS run lock from injected factory or adapter runtime (Refs: ISSUE-057).

        Args:
            manager: Scoped `LiteratureManager` carrying config and runtime.

        Returns:
            Lock context manager, or None if unavailable.
        """
        path = self._lock_path or manager.config.literature_job_lock_path
        if self._lock_factory is not None:
            return self._lock_factory(path)
        open_lock = getattr(manager.runtime, "open_run_lock", None)
        return open_lock(path) if callable(open_lock) else None

    @staticmethod
    def _release_run_lock(run_lock: AbstractContextManager[Any] | None) -> None:
        """Release a held OS run lock if present (Refs: ISSUE-057).

        Args:
            run_lock: Lock context manager acquired prior to execution, or None.
        """
        if run_lock is None:
            return
        try:
            run_lock.__exit__(None, None, None)
        except Exception as exc:  # pragma: no cover - defensive cleanup
            logger.warning("Failed to release literature run lock: %s", exc)

    def _close_stale_in_manager(self, manager: LiteratureManager) -> int:
        """Close stale `running` jobs only after acquiring the process lock (Refs: ISSUE-057).

        Args:
            manager: Scoped `LiteratureManager`.

        Returns:
            Count of stale jobs closed.
        """
        run_lock = self._build_run_lock(manager)
        if run_lock is None:
            return manager.lit_repo.close_stale_jobs("前次程序已中斷，工作未完成")
        with run_lock:
            return manager.lit_repo.close_stale_jobs("前次程序已中斷，工作未完成")

    def _close_stale_on_startup(self) -> None:
        """Close leftover `running` jobs only if no live runner owns the lock (Refs: ISSUE-054, ISSUE-057)."""
        try:
            with self._manager_scope() as manager:
                closed = self._close_stale_in_manager(manager)
            if closed:
                logger.warning("Closed %d stale running literature job(s) on startup", closed)
        except AlreadyRunningError:
            logger.info("Another process holds the literature run lock; skipping stale job cleanup")
        except Exception as exc:
            logger.debug("Skipped stale literature job cleanup on startup: %s", exc)

    def is_running(self) -> bool:
        """Return True when a background literature job is active.

        Returns:
            Boolean indicating active worker thread.
        """
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def live_stage(self) -> tuple[str, str]:
        """Return `(current_key, stage_label)` for the active job, or `("", "")`.

        Returns:
            Tuple of key and stage string.
        """
        with self._lock:
            if self._live is None:
                return "", ""
            return self._live.current_key, self._live.stage

    def _acquire_and_create_job(
        self, kind: str, opts: JobRunOptions
    ) -> tuple[Job, AbstractContextManager[Any] | None]:
        """Acquire the cross-process lock before creating the `running` job record (Refs: ISSUE-057).

        Args:
            kind: Job kind label.
            opts: Execution options.

        Returns:
            Tuple of `(created_job, acquired_run_lock)`.
        """
        with self._manager_scope() as manager:
            run_lock = self._build_run_lock(manager)
            if run_lock is not None:
                run_lock.__enter__()
            try:
                total = len(opts.keys) if opts.keys is not None else len(manager.lit_repo.list_items())
                job = manager.lit_repo.start_job(kind=kind, total=total, message="準備處理文獻…")
            except BaseException:
                self._release_run_lock(run_lock)
                raise
            return job, run_lock

    def start(self, kind: str, opts: JobRunOptions | None = None) -> Job:
        """Start a background literature job if none is currently running.

        Args:
            kind: Job kind label (`download`, `identify`, `interactive`, `retry`).
            opts: Execution options.

        Returns:
            The newly created `Job` record.

        Raises:
            AlreadyRunningError: When another literature job is already running.
        """
        active_opts = opts or JobRunOptions()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise AlreadyRunningError("Another literature fetch job is already running.")
            job, run_lock = self._acquire_and_create_job(kind, active_opts)
            self._live = _LiveProgress(job_id=job.id, total=job.total)
            thread = threading.Thread(
                target=self._run_worker,
                args=(job.id, active_opts, run_lock),
                daemon=True,
                name=f"lit-job-{job.id}",
            )
            self._thread = thread
            try:
                thread.start()
            except BaseException:
                self._release_run_lock(run_lock)
                self._mark_job_failed(job.id, "工作執行緒啟動失敗")
                self._live = None
                self._thread = None
                raise
            return job

    def _mark_job_failed(self, job_id: int, message: str) -> None:
        """Record `JobState.FAILED` in the repository for a failed worker job.

        Args:
            job_id: Persisted job ID.
            message: Failure message.
        """
        with self._manager_scope() as manager:
            manager.lit_repo.finish_job(job_id, JobState.FAILED, message)

    def _record_progress(self, lit_repo: LiteratureRepoProtocol, job_id: int, done: int, label: str) -> None:
        """Update in-memory and DB progress for the active job.

        Args:
            lit_repo: Active literature repository.
            job_id: Job primary key.
            done: Completed item count.
            label: Formatted progress message.
        """
        key, _, stage = label.partition("：")
        with self._lock:
            total = self._live.total if self._live else 0
            self._live = _LiveProgress(job_id=job_id, current_key=key, stage=stage, done=done, total=total)
        lit_repo.update_job(job_id, done=done, message=label)

    def _batch_options(
        self, manager: LiteratureManager, job_id: int, opts: JobRunOptions
    ) -> ProcessBatchOptions:
        """Translate job options into manager batch options that report progress to this job.

        Args:
            manager: Active `LiteratureManager`.
            job_id: Persisted job ID.
            opts: Execution options.

        Returns:
            Batch options with a progress callback bound to `job_id`.
        """

        def _progress(done: int, _total: int, key: str, stage: str) -> None:
            """Forward one progress update to the job record.

            Args:
                done: Completed item count.
                _total: Total item count (tracked separately).
                key: Current item key.
                stage: Current stage label.
            """
            self._record_progress(manager.lit_repo, job_id, done, f"{key}：{stage}")

        return ProcessBatchOptions(
            keys=opts.keys,
            refresh_keys=opts.refresh_keys,
            interactive=opts.interactive,
            identify_only=opts.identify_only,
            no_browser=opts.no_browser,
            progress_cb=_progress,
        )

    def _run_worker(
        self, job_id: int, opts: JobRunOptions, run_lock: AbstractContextManager[Any] | None = None
    ) -> None:
        """Execute the literature batch inside a worker thread, releasing `run_lock` on exit.

        Args:
            job_id: Persisted job ID.
            opts: Execution options.
            run_lock: Acquired cross-process run lock to release in `finally`.
        """
        try:
            with self._manager_scope() as manager:
                processed = manager.process_items(self._batch_options(manager, job_id, opts))
                manager.lit_repo.finish_job(job_id, JobState.DONE, f"已完成 {len(processed)} 筆文獻")
        except BaseException as exc:
            logger.exception("Literature background job %d failed: %s", job_id, exc)
            self._mark_job_failed(job_id, str(exc) or type(exc).__name__)
            if not isinstance(exc, Exception):
                raise
        finally:
            self._release_run_lock(run_lock)
            with self._lock:
                self._live = None
            if opts.on_done is not None:
                opts.on_done()

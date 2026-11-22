"""Single-flight background job runner for literature fetch batches (SPEC-012)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

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

    def __init__(self, manager_scope: Callable[[], AbstractContextManager[LiteratureManager]]) -> None:
        """Initialize the job runner with a context-managed `LiteratureManager` factory.

        Args:
            manager_scope: Callable returning a context manager that yields `LiteratureManager`.
        """
        self._manager_scope = manager_scope
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._live: _LiveProgress | None = None

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
            with self._manager_scope() as manager:
                total = (
                    len(active_opts.keys)
                    if active_opts.keys is not None
                    else len(manager.lit_repo.list_items())
                )
                job = manager.lit_repo.start_job(kind=kind, total=total, message="準備處理文獻…")
            self._live = _LiveProgress(job_id=job.id, total=total)
            thread = threading.Thread(
                target=self._run_worker,
                args=(job.id, active_opts),
                daemon=True,
                name=f"lit-job-{job.id}",
            )
            self._thread = thread
            thread.start()
            return job

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

    def _run_worker(self, job_id: int, opts: JobRunOptions) -> None:
        """Execute the literature batch inside a worker thread.

        Args:
            job_id: Persisted job ID.
            opts: Execution options.
        """
        try:
            with self._manager_scope() as manager:
                batch_opts = ProcessBatchOptions(
                    keys=opts.keys,
                    refresh_keys=opts.refresh_keys,
                    interactive=opts.interactive,
                    identify_only=opts.identify_only,
                    no_browser=opts.no_browser,
                    progress_cb=lambda d, _t, k, s: self._record_progress(
                        manager.lit_repo, job_id, d, f"{k}：{s}"
                    ),
                )
                processed = manager.process_items(batch_opts)
                manager.lit_repo.finish_job(job_id, JobState.DONE, f"已完成 {len(processed)} 筆文獻")
        except Exception as exc:
            logger.exception("Literature background job %d failed: %s", job_id, exc)
            with self._manager_scope() as manager:
                manager.lit_repo.finish_job(job_id, JobState.FAILED, str(exc))
        finally:
            with self._lock:
                self._live = None
            if opts.on_done is not None:
                opts.on_done()

"""Protocol interfaces for literature repository and adapter runtime (dependency inversion)."""

from __future__ import annotations

from contextlib import AbstractContextManager, ExitStack
from pathlib import Path
from typing import Any, Protocol

from notebooklm_batch_studio.domain.literature.tracker import Job, JobState, TrackedItem
from notebooklm_batch_studio.services.literature.literature import Sources
from notebooklm_batch_studio.services.literature.reference_builder import WorkResolver


class LiteratureRepoProtocol(Protocol):
    """Repository protocol for tracked literature items and jobs."""

    def list_items(self, course_code: str | None = None) -> list[TrackedItem]:
        """List tracked items.

        Args:
            course_code: Optional course filter.

        Returns:
            List of tracked items.
        """
        ...

    def get_item(self, key: str) -> TrackedItem | None:
        """Get one item by key.

        Args:
            key: Literature item key.

        Returns:
            TrackedItem or None.
        """
        ...

    def upsert_item(self, item: TrackedItem, position: int | None = None) -> None:
        """Insert or update an item.

        Args:
            item: Tracked item to save.
            position: Optional display order position.
        """
        ...

    def replace_key(self, old_key: str, item: TrackedItem) -> None:
        """Replace an item's primary key.

        Args:
            old_key: Previous primary key.
            item: Updated item carrying the new key.
        """
        ...

    def delete_item(self, key: str) -> bool:
        """Delete an item by key.

        Args:
            key: Literature item key.

        Returns:
            True if deleted.
        """
        ...

    def start_job(self, kind: str, total: int, message: str = "") -> Job:
        """Create a running job.

        Args:
            kind: Job kind label.
            total: Total items in batch.
            message: Initial status message.

        Returns:
            Created Job entity.
        """
        ...

    def update_job(self, job_id: int, done: int, message: str) -> None:
        """Update job progress.

        Args:
            job_id: Job primary key.
            done: Completed items count.
            message: Current status message.
        """
        ...

    def finish_job(self, job_id: int, state: JobState, message: str = "") -> Job | None:
        """Finish a job.

        Args:
            job_id: Job primary key.
            state: Final JobState.
            message: Completion or error message.

        Returns:
            Updated Job or None.
        """
        ...

    def latest_job(self) -> Job | None:
        """Return latest job.

        Returns:
            Most recent Job or None.
        """
        ...

    def close_stale_jobs(self, message: str = "前次程序已中斷，工作未完成") -> int:
        """Mark leftover `running` jobs as failed on startup (Refs: ISSUE-054).

        Args:
            message: Status message recorded on closed jobs.

        Returns:
            Number of closed jobs.
        """
        ...


class LiteratureRuntimeProtocol(Protocol):
    """Adapter-provided runtime for HTTP/Playwright sources and Markdown/APA formatting."""

    def build_resolver(self, stack: ExitStack) -> WorkResolver:
        """Create a WorkResolver managed by `stack`.

        Args:
            stack: Active ExitStack.

        Returns:
            Configured WorkResolver.
        """
        ...

    def open_run_lock(self, path: Path) -> AbstractContextManager[Any]:
        """Create a cross-process run lock context manager for `path` (Refs: ISSUE-057).

        Args:
            path: Lock file path provided by configuration.

        Returns:
            Context manager enforcing mutual exclusion across OS processes.
        """
        ...

    def open_batch_context(
        self, stack: ExitStack, need_browser: bool, interactive: bool
    ) -> tuple[Any, Any, WorkResolver]:
        """Open shared HTTP client, optional browser, and combined resolver.

        Args:
            stack: Active ExitStack.
            need_browser: Whether to launch Chrome.
            interactive: Whether to wait for manual verification.

        Returns:
            Tuple of `(http_client, browser_or_none, work_resolver)`.
        """
        ...

    def build_sources(self, folder: Path, client: Any, browser: Any, progress_cb: Any) -> Sources:
        """Assemble `Sources` for one reference.

        Args:
            folder: Destination folder.
            client: Shared HTTP client.
            browser: Optional browser fetcher.
            progress_cb: Progress callback.

        Returns:
            Configured Sources dataclass.
        """
        ...

    def render_report(self, items: list[TrackedItem], folder_label: str, stamp: str) -> str:
        """Render Markdown report.

        Args:
            items: Tracked items.
            folder_label: Relative folder label.
            stamp: Timestamp string.

        Returns:
            Markdown report text.
        """
        ...

    def sort_key(self, item: TrackedItem) -> str:
        """Return APA 7 sort key.

        Args:
            item: Tracked item.

        Returns:
            Sort key string.
        """
        ...

    def format_notes_and_source(self, item: TrackedItem) -> tuple[str, str, str]:
        """Return `(status_label, source_label, translated_notes)`.

        Args:
            item: Tracked item.

        Returns:
            Tuple of `(status_label, source_label, notes)`.
        """
        ...

    def extract_pdf_hint(self, path: Path) -> str:
        """Extract a DOI, title, or readable stem from a local PDF file.

        Args:
            path: Local PDF path.

        Returns:
            Search query or DOI string.
        """
        ...

"""High-level literature management service: add, identify, download, export, and import to courses.

`LiteratureManager` combines the identify / download pipeline defined here with the archiving
(`archive.py`) and reporting (`export.py`) mixins, which share `manager_base.LiteratureManagerBase`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, replace
from typing import Any

from notebooklm_batch_studio.domain.literature.literature import DownloadOutcome, DownloadStatus, has_cjk
from notebooklm_batch_studio.domain.literature.tracker import ItemStatus, TrackedItem
from notebooklm_batch_studio.domain.study_hierarchy import (
    DEFAULT_LITERATURE_CATEGORY,
    DEFAULT_LITERATURE_SUBFOLDER,
)
from notebooklm_batch_studio.services.literature.archive import LiteratureArchiveMixin
from notebooklm_batch_studio.services.literature.export import LiteratureExportMixin, apa_to_html
from notebooklm_batch_studio.services.literature.literature import download_reference
from notebooklm_batch_studio.services.literature.reference_builder import WorkResolver, resolve_entry

__all__ = ["LiteratureManager", "ProcessBatchOptions", "apa_to_html"]

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str, str], None]


@dataclass(frozen=True)
class ProcessBatchOptions:
    """Options for `LiteratureManager.process_items`.

    Attributes:
        keys: Optional list of item keys; None selects pending/review items.
        refresh_keys: Optional set of keys to upgrade from author copy to publisher VoR.
        interactive: Launch visible Chrome for manual CAPTCHA/OpenAthens login.
        identify_only: Only resolve metadata and APA 7 without downloading PDFs.
        no_browser: Skip Playwright browser sources.
        progress_cb: Optional `(done, total, key, stage)` callback.
    """

    keys: list[str] | None = None
    refresh_keys: frozenset[str] = frozenset()
    interactive: bool = False
    identify_only: bool = False
    no_browser: bool = False
    progress_cb: ProgressCallback | None = None


@dataclass(frozen=True)
class _BatchContext:
    """Open sources shared by every item of one processing batch.

    Attributes:
        client: Shared HTTP client.
        browser: Optional Playwright browser fetcher.
        resolver: Work resolver used for identification.
        opts: Batch options.
    """

    client: Any
    browser: Any
    resolver: WorkResolver
    opts: ProcessBatchOptions


def _status_from_outcome(outcome: DownloadOutcome) -> ItemStatus:
    """Map a `DownloadOutcome` to a persistent `ItemStatus`.

    Args:
        outcome: Result returned by `download_reference`.

    Returns:
        Corresponding `ItemStatus`.
    """
    if outcome.status in (DownloadStatus.DOWNLOADED, DownloadStatus.ALREADY_PRESENT):
        if "author" in outcome.detail.lower() or "preprint" in outcome.detail.lower():
            return ItemStatus.DOWNLOADED_COPY
        return ItemStatus.DOWNLOADED
    if outcome.status == DownloadStatus.MANUAL:
        return ItemStatus.BORROW
    if outcome.status == DownloadStatus.FAILED:
        return ItemStatus.UNAVAILABLE
    return ItemStatus.NEEDS_REVIEW


def _pending_item(key: str, entry: str, placement: tuple[str | None, str, str]) -> TrackedItem:
    """Build a new pending tracker entry for one pasted reference line.

    Args:
        key: Reserved `Unresolved_N` key.
        entry: Reference text as the user wrote it.
        placement: `(course_code, category, subfolder)` the PDF should be filed under.

    Returns:
        New pending `TrackedItem`.
    """
    course_code, category, subfolder = placement
    return TrackedItem(
        key=key,
        input=entry,
        reference=None,
        apa=entry,
        status=ItemStatus.PENDING,
        course_code=course_code or None,
        target_category=category or DEFAULT_LITERATURE_CATEGORY,
        target_subfolder=subfolder or DEFAULT_LITERATURE_SUBFOLDER,
    )


def _step_forwarder(progress_cb: ProgressCallback | None) -> Callable[[str, str], None]:
    """Adapt the batch progress callback to the per-source `(key, step)` callback.

    Args:
        progress_cb: Optional batch progress callback.

    Returns:
        Callback that forwards each source step (or does nothing).
    """

    def _step_cb(key: str, step: str) -> None:
        """Forward one per-source step update.

        Args:
            key: Literature item key.
            step: Current source step label.
        """
        if progress_cb is not None:
            progress_cb(0, 1, key, step)

    return _step_cb


class LiteratureManager(LiteratureArchiveMixin, LiteratureExportMixin):
    """Coordinates literature tracking, metadata resolution, PDF fetching, and course import."""

    def _next_unresolved_key(self, taken: set[str], start: int) -> tuple[str, int]:
        """Generate the next unused `Unresolved_N` key.

        Args:
            taken: Set of already-used keys.
            start: Starting index counter.

        Returns:
            Tuple of `(unique_key, next_counter)`.
        """
        idx = start
        while f"Unresolved_{idx}" in taken:
            idx += 1
        key = f"Unresolved_{idx}"
        taken.add(key)
        return key, idx + 1

    def add_entries(
        self,
        raw_text: str,
        course_code: str | None = None,
        category: str = DEFAULT_LITERATURE_CATEGORY,
        subfolder: str = DEFAULT_LITERATURE_SUBFOLDER,
    ) -> list[TrackedItem]:
        """Parse pasted lines/paragraphs and add new pending literature items.

        Args:
            raw_text: Multi-line or paragraph-separated APA/DOI/title entries.
            course_code: Optional course code to link these items to.
            category: Study category (default `01 Materials`).
            subfolder: Subfolder under category (default `Literature_Review`).

        Returns:
            List of newly added `TrackedItem` instances.
        """
        entries = [line.strip() for line in re.split(r"\r?\n+", raw_text) if line.strip()]
        existing = {item.input.strip(): item for item in self.lit_repo.list_items()}
        taken_keys = {item.key for item in existing.values()}
        added: list[TrackedItem] = []
        next_idx = len(existing) + 1
        for entry in (e for e in entries if e not in existing):
            key, next_idx = self._next_unresolved_key(taken_keys, next_idx)
            item = _pending_item(key, entry, (course_code, category, subfolder))
            self.lit_repo.upsert_item(item)
            added.append(item)
        logger.info("Added %d literature items (course=%s)", len(added), course_code)
        return added

    def _resolve(self, item: TrackedItem, resolver: WorkResolver | None, taken: set[str]) -> Any:
        """Run reference resolution with the given, preset, or freshly built resolver.

        Args:
            item: Tracked item to identify.
            resolver: Optional resolver reused across a batch.
            taken: Keys already used by other items.

        Returns:
            Resolution result from `resolve_entry`.
        """
        active = resolver or self._work_resolver
        if active is not None:
            return resolve_entry(item.input, active, taken)
        assert self.runtime is not None
        with ExitStack() as stack:
            return resolve_entry(item.input, self.runtime.build_resolver(stack), taken)

    def _mark_unresolved(self, item: TrackedItem, note: str) -> TrackedItem:
        """Persist an item whose reference could not be identified.

        Args:
            item: Tracked item.
            note: Resolver note explaining the failure.

        Returns:
            Updated item (status kept when a PDF already exists).
        """
        keep_status = item.status if item.file else ItemStatus.NOT_FOUND
        note_text = "已保存 PDF，尚未在 Crossref 找到對應來源" if item.file else (note or "not found")
        updated = replace(item, status=keep_status, note=note_text)
        self.lit_repo.upsert_item(updated)
        return updated

    def identify_item(self, item: TrackedItem, resolver: WorkResolver | None = None) -> TrackedItem:
        """Resolve metadata/DOI and APA 7 formatting for a single `TrackedItem`.

        Args:
            item: Tracked item to identify.
            resolver: Optional `WorkResolver` to reuse across a batch.

        Returns:
            Updated `TrackedItem` persisted to the database.
        """
        if item.reference is not None and item.apa:
            return item
        taken = {i.key for i in self.lit_repo.list_items() if i.key != item.key}
        res = self._resolve(item, resolver, taken)
        if res.reference is None:
            return self._mark_unresolved(item, res.note)
        reopened = item.status == ItemStatus.NOT_FOUND and not item.file
        updated = replace(
            item,
            key=res.reference.key,
            reference=res.reference,
            apa=res.apa or res.reference.citation,
            check=res.note,
            source=item.source or (f"https://doi.org/{res.reference.doi}" if res.reference.doi else ""),
            status=ItemStatus.PENDING if reopened else item.status,
        )
        self.lit_repo.replace_key(item.key, updated)
        return updated

    def _process_one(self, idx: int, raw_item: TrackedItem, ctx: _BatchContext) -> TrackedItem:
        """Identify one item and, unless identify-only, download its PDF.

        Args:
            idx: Position in the batch (for progress reporting).
            raw_item: Item as stored before processing.
            ctx: Shared batch context.

        Returns:
            Updated item.
        """
        if ctx.opts.progress_cb:
            ctx.opts.progress_cb(idx, len(ctx.opts.keys or []), raw_item.key, "辨識中")
        item = self.identify_item(raw_item, resolver=ctx.resolver)
        if ctx.opts.identify_only or item.reference is None:
            return item
        return self._download_one_item(item, ctx, refresh=item.key in ctx.opts.refresh_keys)

    def process_items(self, opts: ProcessBatchOptions | None = None) -> list[TrackedItem]:
        """Identify and download pending (or selected) literature items.

        Args:
            opts: Batch processing options.

        Returns:
            List of updated `TrackedItem` objects.
        """
        active_opts = opts or ProcessBatchOptions()
        target_keys = list(active_opts.keys) if active_opts.keys is not None else None
        if target_keys is None and active_opts.refresh_keys:
            target_keys = sorted(active_opts.refresh_keys)
        targets = self._select_targets(target_keys)
        if not targets or self.runtime is None:
            return []
        need_browser = (not active_opts.no_browser) and (
            not active_opts.identify_only or any(has_cjk(i.input) for i in targets)
        )
        batch_opts = replace(active_opts, keys=[t.key for t in targets])
        with ExitStack() as stack:
            client, browser, resolver = self.runtime.open_batch_context(
                stack, need_browser=need_browser, interactive=active_opts.interactive
            )
            ctx = _BatchContext(client, browser, self._work_resolver or resolver, batch_opts)
            return [self._process_one(idx, raw_item, ctx) for idx, raw_item in enumerate(targets)]

    def reidentify_item(self, key: str, new_input: str) -> TrackedItem | None:
        """Replace an item's input text and re-run Crossref identification.

        Args:
            key: Existing literature item key.
            new_input: Corrected APA, title, or DOI string.

        Returns:
            Updated `TrackedItem` or None if key does not exist.
        """
        item = self.lit_repo.get_item(key)
        if item is None:
            return None
        reset = replace(item, input=new_input.strip(), reference=None, apa="", status=ItemStatus.PENDING)
        self.lit_repo.upsert_item(reset)
        return self.identify_item(reset)

    def _select_targets(self, keys: list[str] | None) -> list[TrackedItem]:
        """Select items to process based on explicit keys or pending/review status.

        Args:
            keys: Optional explicit keys.

        Returns:
            Ordered list of `TrackedItem` objects.
        """
        all_items = self.lit_repo.list_items()
        if keys is not None:
            wanted = set(keys)
            return [item for item in all_items if item.key in wanted]
        return [
            item
            for item in all_items
            if item.reference is None
            or item.status in (ItemStatus.PENDING, ItemStatus.NEEDS_REVIEW, ItemStatus.NOT_FOUND)
        ]

    def _download_one_item(self, item: TrackedItem, ctx: _BatchContext, refresh: bool = False) -> TrackedItem:
        """Run the download pipeline for a single identified `TrackedItem`.

        Args:
            item: Identified item with `reference` populated.
            ctx: Shared batch context (HTTP client, browser, progress callback).
            refresh: When True, attempt to replace an author copy with publisher VoR.

        Returns:
            Updated and persisted `TrackedItem`.
        """
        assert item.reference is not None and self.runtime is not None
        folder = self.resolve_target_dir(item)
        sources = self.runtime.build_sources(
            folder, ctx.client, ctx.browser, _step_forwarder(ctx.opts.progress_cb)
        )
        outcome = download_reference(item.reference, sources, refresh=refresh)
        updated = replace(
            item,
            status=_status_from_outcome(outcome),
            file=outcome.path.name if outcome.path else item.file,
            note=outcome.detail,
            source=outcome.source,
        )
        self.lit_repo.upsert_item(updated)
        return updated

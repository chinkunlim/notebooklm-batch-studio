"""High-level literature management service: add, identify, download, export, and import to courses."""

from __future__ import annotations

import html
import logging
import re
import shutil
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.literature.literature import DownloadOutcome, DownloadStatus, has_cjk
from notebooklm_batch_studio.domain.literature.tracker import ItemStatus, TrackedItem
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol
from notebooklm_batch_studio.domain.study_hierarchy import (
    DEFAULT_LITERATURE_CATEGORY,
    DEFAULT_LITERATURE_SUBFOLDER,
    resolve_literature_dir,
)
from notebooklm_batch_studio.services.literature.literature import download_reference
from notebooklm_batch_studio.services.literature.protocols import (
    LiteratureRepoProtocol,
    LiteratureRuntimeProtocol,
)
from notebooklm_batch_studio.services.literature.reference_builder import WorkResolver, resolve_entry

logger = logging.getLogger(__name__)


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
    progress_cb: Callable[[int, int, str, str], None] | None = None


def apa_to_html(apa: str) -> str:
    """Render APA 7 Markdown italics (`*...*`) as escaped HTML `<i>...</i>`.

    Args:
        apa: APA 7 string with optional Markdown italics.

    Returns:
        HTML-safe string with `<i>` tags.
    """
    return re.sub(r"\*([^*]+)\*", r"<i>\1</i>", html.escape(apa))


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


class LiteratureManager:
    """Coordinates literature tracking, metadata resolution, PDF fetching, and course import."""

    def __init__(
        self,
        config: AppConfig,
        lit_repo: LiteratureRepoProtocol,
        course_repo: CourseRepositoryProtocol,
        runtime: LiteratureRuntimeProtocol | None = None,
    ) -> None:
        """Initialize the manager with configuration, repositories, and adapter runtime.

        Args:
            config: Application configuration.
            lit_repo: Persistence repository for literature items and jobs.
            course_repo: Persistence repository for courses.
            runtime: Adapter runtime providing HTTP/browser sources and formatters.
        """
        self.config = config
        self.lit_repo = lit_repo
        self.course_repo = course_repo
        self.runtime = runtime
        self._work_resolver: WorkResolver | None = None

    def resolve_target_dir(self, item: TrackedItem) -> Path:
        """Resolve the filesystem folder where an item's PDF should be stored.

        Args:
            item: Tracked literature item.

        Returns:
            Course category/subfolder directory when linked to a course,
            otherwise `config.literature_dir`.
        """
        if item.course_code:
            course = self.course_repo.get_course(item.course_code)
            if course is not None:
                base = Path(course.study_dir) if course.study_dir else Path(course.source_dir)
                target = resolve_literature_dir(base, item.target_category, item.target_subfolder)
                target.mkdir(parents=True, exist_ok=True)
                return target
        self.config.literature_dir.mkdir(parents=True, exist_ok=True)
        return self.config.literature_dir

    def resolve_pdf_path(self, key: str) -> Path | None:
        """Return the existing PDF file path for a literature item, if present on disk.

        Args:
            key: Literature item key.

        Returns:
            Path to the PDF file, or None.
        """
        item = self.lit_repo.get_item(key)
        if item is None or not item.file:
            return None
        folder = self.resolve_target_dir(item)
        candidate = (folder / item.file).resolve()
        if candidate.is_relative_to(folder.resolve()) and candidate.is_file():
            return candidate
        fallback = (self.config.literature_dir / item.file).resolve()
        return fallback if fallback.is_file() else None

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
            category: Study category (default `01 Material`).
            subfolder: Subfolder under category (default `Literature_Review`).

        Returns:
            List of newly added `TrackedItem` instances.
        """
        entries = [line.strip() for line in re.split(r"\r?\n+", raw_text) if line.strip()]
        existing = {item.input.strip(): item for item in self.lit_repo.list_items()}
        taken_keys = {item.key for item in existing.values()}
        added: list[TrackedItem] = []
        next_idx = len(existing) + 1

        for entry in entries:
            if entry in existing:
                continue
            key, next_idx = self._next_unresolved_key(taken_keys, next_idx)
            item = TrackedItem(
                key=key,
                input=entry,
                reference=None,
                apa=entry,
                status=ItemStatus.PENDING,
                course_code=course_code or None,
                target_category=category or DEFAULT_LITERATURE_CATEGORY,
                target_subfolder=subfolder or DEFAULT_LITERATURE_SUBFOLDER,
            )
            self.lit_repo.upsert_item(item)
            added.append(item)

        logger.info("Added %d literature items (course=%s)", len(added), course_code)
        return added

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
        active = resolver or self._work_resolver
        if active is not None:
            res = resolve_entry(item.input, active, taken)
        else:
            assert self.runtime is not None
            with ExitStack() as stack:
                res = resolve_entry(item.input, self.runtime.build_resolver(stack), taken)

        if res.reference is None:
            keep_status = item.status if item.file else ItemStatus.NOT_FOUND
            note_text = "已保存 PDF，尚未在 Crossref 找到對應來源" if item.file else (res.note or "not found")
            updated = replace(item, status=keep_status, note=note_text)
            self.lit_repo.upsert_item(updated)
            return updated

        new_source = item.source or (f"https://doi.org/{res.reference.doi}" if res.reference.doi else "")
        next_status = (
            item.status
            if item.file
            else (ItemStatus.PENDING if item.status == ItemStatus.NOT_FOUND else item.status)
        )
        updated = replace(
            item,
            key=res.reference.key,
            reference=res.reference,
            apa=res.apa or res.reference.citation,
            check=res.note,
            source=new_source,
            status=next_status,
        )
        self.lit_repo.replace_key(item.key, updated)
        return updated

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
        results: list[TrackedItem] = []
        with ExitStack() as stack:
            client, browser, resolver = self.runtime.open_batch_context(
                stack, need_browser=need_browser, interactive=active_opts.interactive
            )
            active_resolver = self._work_resolver or resolver
            for idx, raw_item in enumerate(targets):
                if active_opts.progress_cb:
                    active_opts.progress_cb(idx, len(targets), raw_item.key, "辨識中")
                item = self.identify_item(raw_item, resolver=active_resolver)
                if active_opts.identify_only or item.reference is None:
                    results.append(item)
                    continue
                is_refresh = item.key in active_opts.refresh_keys
                results.append(
                    self._download_one_item(
                        item, client, browser, active_opts.progress_cb, refresh=is_refresh
                    )
                )
        return results

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

    def import_to_course(
        self,
        key: str,
        course_code: str | None = None,
        category: str | None = None,
        subfolder: str | None = None,
    ) -> TrackedItem:
        """Ensure a downloaded PDF is stored in the linked course directory and marked imported.

        Args:
            key: Literature item key.
            course_code: Optional course code override if item was not yet linked.
            category: Optional target study category override.
            subfolder: Optional target subfolder override.

        Returns:
            Updated `TrackedItem`.

        Raises:
            ValueError: When item or target course is missing, or PDF is not downloaded yet.
        """
        item = self.lit_repo.get_item(key)
        if item is None:
            raise ValueError(f"Literature item not found: {key}")
        target_code = course_code or item.course_code
        if not target_code or self.course_repo.get_course(target_code) is None:
            raise ValueError("Please link a valid course before importing.")
        src_pdf = self.resolve_pdf_path(key)
        if src_pdf is None or not src_pdf.is_file():
            raise ValueError("PDF has not been downloaded yet.")

        old_reviews_dir = src_pdf.parent / "reviews"
        updated_item = replace(
            item,
            course_code=target_code,
            target_category=category or item.target_category,
            target_subfolder=subfolder if subfolder is not None else item.target_subfolder,
        )
        dest_dir = self.resolve_target_dir(updated_item)
        dest_pdf = dest_dir / src_pdf.name
        if src_pdf.resolve() != dest_pdf.resolve():
            dest_pdf.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_pdf), str(dest_pdf))
            self._move_review_file(item.key, old_reviews_dir, dest_dir / "reviews", item.review_markdown)

        saved = replace(updated_item, file=dest_pdf.name, imported_to_course=True)
        self.lit_repo.upsert_item(saved)
        logger.info("Archived literature %s into course %s (%s)", key, target_code, dest_pdf)
        return saved

    def _move_review_file(self, key: str, src_reviews: Path, dst_reviews: Path, review_markdown: str) -> None:
        """Move `<key>_Literature_Review.md` alongside the PDF when archiving/unarchiving.

        Args:
            key: Literature item key.
            src_reviews: Source `reviews/` directory.
            dst_reviews: Destination `reviews/` directory.
            review_markdown: Stored Markdown review text (written if file missing).
        """
        fname = f"{key}_Literature_Review.md"
        src_file = src_reviews / fname
        dst_file = dst_reviews / fname
        if src_file.is_file():
            dst_reviews.mkdir(parents=True, exist_ok=True)
            if src_file.resolve() != dst_file.resolve():
                shutil.move(str(src_file), str(dst_file))
        elif review_markdown:
            dst_reviews.mkdir(parents=True, exist_ok=True)
            dst_file.write_text(review_markdown, encoding="utf-8")

    def unarchive_item(self, key: str) -> TrackedItem:
        """Move an archived literature PDF back to the unarchived staging folder.

        Args:
            key: Literature item key.

        Returns:
            Updated unarchived `TrackedItem`.

        Raises:
            ValueError: When item is not found.
        """
        item = self.lit_repo.get_item(key)
        if item is None:
            raise ValueError(f"Literature item not found: {key}")
        src_pdf = self.resolve_pdf_path(key)
        self.config.literature_dir.mkdir(parents=True, exist_ok=True)
        if src_pdf is not None and src_pdf.is_file():
            old_reviews_dir = src_pdf.parent / "reviews"
            dest_pdf = self.config.literature_dir / src_pdf.name
            if src_pdf.resolve() != dest_pdf.resolve():
                shutil.move(str(src_pdf), str(dest_pdf))
                self._move_review_file(
                    key, old_reviews_dir, self.config.literature_dir / "reviews", item.review_markdown
                )
        saved = replace(item, course_code=None, imported_to_course=False)
        self.lit_repo.upsert_item(saved)
        logger.info("Moved literature %s back to unarchived folder", key)
        return saved

    def _register_dir_pdfs(
        self,
        folder: Path,
        known_files: set[str],
        taken_keys: set[str],
        course_code: str | None = None,
    ) -> list[str]:
        """Register any untracked `*.pdf` files found in `folder` into `lit_repo`.

        Args:
            folder: Directory to scan.
            known_files: Set of already-tracked PDF filenames (mutated in place).
            taken_keys: Set of already-used item keys (mutated in place).
            course_code: Optional course code if scanning a course's `Literature_Review`.

        Returns:
            List of newly registered item keys.
        """
        if not folder.is_dir():
            return []
        added_keys: list[str] = []
        for pdf in sorted(folder.glob("*.pdf")):
            if pdf.name.startswith(".") or pdf.name in known_files:
                continue
            key = pdf.stem
            suffix = 2
            while key in taken_keys:
                key = f"{pdf.stem}_{suffix}"
                suffix += 1
            taken_keys.add(key)
            known_files.add(pdf.name)
            hint = self.runtime.extract_pdf_hint(pdf) if self.runtime else pdf.stem.replace("_", " ")
            item = TrackedItem(
                key=key,
                input=hint,
                reference=None,
                apa=pdf.stem,
                status=ItemStatus.DOWNLOADED,
                file=pdf.name,
                note="auto-discovered from folder (pending source lookup)",
                course_code=course_code,
                target_category=DEFAULT_LITERATURE_CATEGORY,
                target_subfolder=DEFAULT_LITERATURE_SUBFOLDER,
                imported_to_course=bool(course_code),
            )
            self.lit_repo.upsert_item(item)
            added_keys.append(key)
        return added_keys

    def sync_untracked_pdfs(self) -> list[str]:
        """Auto-register untracked PDFs in `scratch/literature` and course `Literature_Review` dirs.

        Returns:
            List of newly registered item keys.
        """
        self.config.literature_dir.mkdir(parents=True, exist_ok=True)
        items = self.lit_repo.list_items()
        known_files = {item.file for item in items if item.file}
        taken_keys = {item.key for item in items}
        added_keys = self._register_dir_pdfs(self.config.literature_dir, known_files, taken_keys)
        for course in self.course_repo.list_courses():
            base = Path(course.study_dir) if course.study_dir else Path(course.source_dir)
            lit_dir = resolve_literature_dir(base, DEFAULT_LITERATURE_CATEGORY, DEFAULT_LITERATURE_SUBFOLDER)
            added_keys.extend(
                self._register_dir_pdfs(lit_dir, known_files, taken_keys, course_code=course.code)
            )
        if added_keys:
            logger.info("Auto-registered %d untracked literature PDFs", len(added_keys))
        return added_keys

    def export_report(self, course_code: str | None = None) -> str:
        """Render the Markdown download report for all or course-filtered items.

        Args:
            course_code: Optional course filter.

        Returns:
            Markdown report content.
        """
        items = self.lit_repo.list_items(course_code=course_code)
        stamp = f"{datetime.now():%Y-%m-%d %H:%M}"
        if self.runtime is not None:
            return self.runtime.render_report(items, "Literature_Review", stamp)
        return "\n".join(f"- [{i.status.value}] {i.apa}" for i in items)

    def export_apa_list(
        self, course_code: str | None = None, keys: list[str] | None = None
    ) -> dict[str, Any]:
        """Return sorted APA 7 citations in plain text and HTML (preserving italics).

        Args:
            course_code: Optional course filter.
            keys: Optional list of item keys to include; None includes all items.

        Returns:
            Dictionary with `count`, `plain`, and `html` keys.
        """
        raw = self.lit_repo.list_items(course_code=course_code)
        if keys:
            wanted = set(keys)
            raw = [item for item in raw if item.key in wanted]
        items = sorted(raw, key=self.runtime.sort_key) if self.runtime else sorted(raw, key=lambda x: x.apa)
        apas = [item.apa for item in items if item.apa]
        return {
            "count": len(apas),
            "plain": "\n\n".join(apas),
            "html": "".join(f"<p>{apa_to_html(apa)}</p>" for apa in apas),
        }

    def serialize_item(self, item: TrackedItem, stage: str = "") -> dict[str, Any]:
        """Serialize a `TrackedItem` for HTTP API and MCP responses.

        Args:
            item: Tracked literature item.
            stage: Live stage label when a job is currently processing this item.

        Returns:
            JSON-serializable dictionary.
        """
        if self.runtime is not None:
            status_label, src_label, notes = self.runtime.format_notes_and_source(item)
        else:
            status_label, src_label, notes = item.status.value, item.source, item.note
        return {
            "key": item.key,
            "input": item.input,
            "apa": item.apa,
            "apa_html": apa_to_html(item.apa),
            "status": item.status.value,
            "status_label": status_label,
            "kind": item.reference.kind.value if item.reference else "",
            "doi": item.reference.doi if item.reference else "",
            "file": item.file,
            "file_url": f"/api/literature/{item.key}/pdf" if item.file else "",
            "source": src_label,
            "notes": notes,
            "stage": stage,
            "course_code": item.course_code,
            "target_category": item.target_category,
            "target_subfolder": item.target_subfolder,
            "imported_to_course": item.imported_to_course,
            "source_id": item.source_id,
            "has_review": bool(item.review_markdown),
            "review_markdown": item.review_markdown,
        }

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

    def _download_one_item(
        self,
        item: TrackedItem,
        client: Any,
        browser: Any,
        progress_cb: Callable[[int, int, str, str], None] | None,
        refresh: bool = False,
    ) -> TrackedItem:
        """Run the download pipeline for a single identified `TrackedItem`.

        Args:
            item: Identified item with `reference` populated.
            client: Shared HTTP client.
            browser: Optional Playwright browser fetcher.
            progress_cb: Optional progress callback.
            refresh: When True, attempt to replace an author copy with publisher VoR.

        Returns:
            Updated and persisted `TrackedItem`.
        """
        assert item.reference is not None and self.runtime is not None
        folder = self.resolve_target_dir(item)

        def _step_cb(key: str, step: str) -> None:
            """Forward per-source step updates to the batch progress callback.

            Args:
                key: Literature item key.
                step: Current source step label.
            """
            if progress_cb is not None:
                progress_cb(0, 1, key, step)

        sources = self.runtime.build_sources(folder, client, browser, _step_cb)
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

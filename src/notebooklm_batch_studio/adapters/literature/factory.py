"""Adapter factory wiring HTTP, OpenAthens, Crossref, and OpenAlex clients into literature services."""

from __future__ import annotations

import logging
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import httpx

from notebooklm_batch_studio.adapters.literature.airiti import AiritiLibrary
from notebooklm_batch_studio.adapters.literature.browser import BrowserPublisherFetcher
from notebooklm_batch_studio.adapters.literature.crossref import CrossrefResolver
from notebooklm_batch_studio.adapters.literature.ebsco import EbscoFetcher
from notebooklm_batch_studio.adapters.literature.files import FilePdfStore
from notebooklm_batch_studio.adapters.literature.http_pdf import HttpPdfFetcher
from notebooklm_batch_studio.adapters.literature.metadata import CombinedResolver
from notebooklm_batch_studio.adapters.literature.openalex import OpenAlexFinder, OpenAlexResolver
from notebooklm_batch_studio.adapters.literature.openlibrary import OpenLibraryBooks
from notebooklm_batch_studio.adapters.literature.pdf_text import PypdfTextReader, extract_pdf_hint
from notebooklm_batch_studio.adapters.literature.report_md import render_report_md
from notebooklm_batch_studio.adapters.literature.tracker_md import (
    STATUS_LABELS,
    apa_sort_key,
    source_name,
    translate_note,
)
from notebooklm_batch_studio.adapters.locks import RunLock
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.literature.tracker import ItemStatus, TrackedItem
from notebooklm_batch_studio.services.literature.literature import PublisherFetcher, Sources
from notebooklm_batch_studio.services.literature.reference_builder import WorkResolver

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) notebooklm-batch-studio/0.1 (academic use)"


class AdapterLiteratureRuntime:
    """Provides adapter-layer resolvers, browser/HTTP sources, and formatting helpers to services."""

    def __init__(self, config: AppConfig) -> None:
        """Store configuration for constructing adapter clients.

        Args:
            config: Application configuration.
        """
        self.config = config

    def build_resolver(self, stack: ExitStack) -> WorkResolver:
        """Create a standalone `CombinedResolver` (Crossref + OpenAlex) managed by `stack`.

        Args:
            stack: Active `ExitStack` managing HTTP client lifetime.

        Returns:
            Configured `WorkResolver`.
        """
        client = stack.enter_context(
            httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60)
        )
        return CombinedResolver([CrossrefResolver(client), OpenAlexResolver(client)])

    def open_run_lock(self, path: Path) -> RunLock:
        """Create an OS-level `RunLock` at `path` for background job runners (Refs: ISSUE-057).

        Args:
            path: Lock file path from configuration.

        Returns:
            Configured `RunLock` context manager.
        """
        return RunLock(path)

    def open_batch_context(
        self, stack: ExitStack, need_browser: bool, interactive: bool
    ) -> tuple[httpx.Client, BrowserPublisherFetcher | None, WorkResolver]:
        """Open shared HTTP client, optional Chrome session, and combined resolver for a batch.

        Args:
            stack: Active `ExitStack`.
            need_browser: Whether to launch Playwright Chrome.
            interactive: Whether to wait for manual CAPTCHA/OpenAthens login.

        Returns:
            Tuple of `(http_client, browser_or_none, work_resolver)`.
        """
        client = stack.enter_context(
            httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60)
        )
        browser: BrowserPublisherFetcher | None = None
        if need_browser:
            wait = 300 if interactive else 0
            browser = BrowserPublisherFetcher(
                self.config.literature_browser_profile_dir,
                self.config.openathens_domain,
                (self.config.library_email, self.config.library_password),
                wait,
            )
            browser.chrome_path = self.config.chrome_path  # SPEC-022: real Chrome + CDP
            stack.enter_context(browser)
        resolvers: list[WorkResolver] = [CrossrefResolver(client), OpenAlexResolver(client)]
        if browser is not None:
            resolvers.append(AiritiLibrary(browser))
        return client, browser, CombinedResolver(resolvers)

    def build_sources(
        self,
        folder: Path,
        client: httpx.Client,
        browser: BrowserPublisherFetcher | None,
        progress_cb: Any,
    ) -> Sources:
        """Assemble `Sources` for downloading one reference into `folder`.

        Args:
            folder: Destination directory for the PDF.
            client: Shared `httpx.Client`.
            browser: Optional Playwright browser fetcher.
            progress_cb: Progress callback `(key, step) -> None`.

        Returns:
            Configured `Sources` dataclass.
        """
        routes: list[PublisherFetcher] = []
        if browser is not None:
            routes.append(AiritiLibrary(browser))
            if self.config.ebsco_profile:
                routes.append(EbscoFetcher(browser, self.config.ebsco_profile))
            routes.append(browser)
        return Sources(
            open_access=OpenAlexFinder(client),
            http=HttpPdfFetcher(client),
            publishers=tuple(routes),
            store=FilePdfStore(folder),
            pdf_text=PypdfTextReader(),
            site=browser,
            books=OpenLibraryBooks(client),
            progress=progress_cb,
        )

    def render_report(self, items: list[TrackedItem], folder_label: str, stamp: str) -> str:
        """Render Markdown report via `adapters.literature.report_md`.

        Args:
            items: Tracked items.
            folder_label: Relative PDF folder label.
            stamp: Timestamp string.

        Returns:
            Markdown report string.
        """
        return render_report_md(items, folder_label, stamp)

    def sort_key(self, item: TrackedItem) -> str:
        """Return APA 7 sort key for a `TrackedItem`.

        Args:
            item: Tracked item.

        Returns:
            Sort key string.
        """
        return apa_sort_key(item)

    def format_notes_and_source(self, item: TrackedItem) -> tuple[str, str, str]:
        """Return `(status_label, source_label, translated_notes)` for UI/API display.

        Args:
            item: Tracked item.

        Returns:
            Tuple of `(status_label, source_label, notes)`.
        """
        status_label = STATUS_LABELS.get(item.status, item.status.value)
        src_label = str(source_name(item.source)) if item.source and item.file else ""
        notes = "；".join(x for x in (translate_note(item.check), translate_note(item.note)) if x)
        return status_label, src_label, notes

    def extract_pdf_hint(self, path: Path) -> str:
        """Extract a DOI, title, or readable stem from a PDF for Crossref/OpenAlex lookup.

        Args:
            path: Local PDF path.

        Returns:
            Search query or DOI string.
        """
        return extract_pdf_hint(path)


def default_status_label(status: ItemStatus) -> str:
    """Return human-readable label for an `ItemStatus`.

    Args:
        status: ItemStatus enum.

    Returns:
        Localized status label.
    """
    return STATUS_LABELS.get(status, status.value)

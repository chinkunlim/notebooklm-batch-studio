"""Gemini Notebook learning sites: chat request, Studio listing and guarded HTML download (SPEC-021).

notebooklm-py has no site API: the site is requested by sending a "make me a site" chat prompt,
appears in Studio as a type-10 item, and its HTML must be downloaded here because the library's
downloader rejects HTML bodies as sign-in pages (Refs: ISSUE-070).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from notebooklm_batch_studio.adapters.notebooklm.errors import _translate_errors
from notebooklm_batch_studio.domain.exceptions import AuthExpiredError
from notebooklm_batch_studio.domain.learning_site import SiteRow, parse_site_row

logger = logging.getLogger(__name__)

MAX_REDIRECTS = 6
_ALLOWED_SUFFIXES = (".google.com", ".googleusercontent.com")
_SIGN_IN_MARKERS = ("accounts.google.com/ServiceLogin", "<title>Sign in")


def _is_google_host(url: str) -> bool:
    """Tell whether a URL is https and on a Google or googleusercontent host.

    Args:
        url: Absolute URL.

    Returns:
        True for `https://*.google.com/...` and `https://*.googleusercontent.com/...`.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host == "google.com" or host.endswith(_ALLOWED_SUFFIXES))


def _check_site_body(url: str, response: httpx.Response) -> str:
    """Validate a final download response and return its HTML text.

    Args:
        url: Final URL that produced the response.
        response: The non-redirect response.

    Returns:
        The HTML text of the site.

    Raises:
        AuthExpiredError: When the response is Google's sign-in page.
        ValueError: When the response is not a successful HTML document.
    """
    if (urlsplit(url).hostname or "") == "accounts.google.com":
        raise AuthExpiredError("Gemini Notebook 登入已過期：下載學習網頁時被導向登入頁")
    if response.status_code != 200:
        raise ValueError(f"learning-site download failed: HTTP {response.status_code}")
    text = response.text
    if any(marker in text for marker in _SIGN_IN_MARKERS):
        raise AuthExpiredError("Gemini Notebook 登入已過期：下載到的是 Google 登入頁")
    head = text.lstrip()[:200].lower()
    is_html = "text/html" in response.headers.get("content-type", "") or head.startswith(
        ("<!doctype html", "<html")
    )
    if not is_html:
        raise ValueError("learning-site download is not an HTML document")
    return text


async def _follow_google_redirects(http: httpx.AsyncClient, url: str) -> tuple[str, httpx.Response]:
    """GET a URL, following at most MAX_REDIRECTS redirects that all stay on Google hosts.

    Args:
        http: Client that does not follow redirects by itself.
        url: Start URL.

    Returns:
        The final URL and its non-redirect response.

    Raises:
        ValueError: When any hop leaves Google or there are too many redirects.
    """
    for _hop in range(MAX_REDIRECTS + 1):
        if not _is_google_host(url):
            raise ValueError(f"learning-site download refused non-Google URL host={urlsplit(url).hostname}")
        response = await http.get(url)
        if not response.is_redirect:
            return url, response
        url = urljoin(url, response.headers.get("location", ""))
    raise ValueError(f"learning-site download exceeded {MAX_REDIRECTS} redirects")


def _write_atomically(path: Path, text: str) -> None:
    """Write text to `<path>.part`, then move it into place.

    Args:
        path: Destination file.
        text: File content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(text, encoding="utf-8")
    os.replace(part, path)


class LearningSiteMixin:
    """`LearningSiteClientProtocol` on top of the adapter's `_client()` and `storage_path`."""

    storage_path: Path
    _site_locks: dict[str, asyncio.Lock]

    def _client(self) -> Any:
        """Return a notebooklm-py client context; implemented by the adapter.

        Raises:
            NotImplementedError: Always; the concrete adapter overrides this.
        """
        raise NotImplementedError

    def site_lock(self, notebook_id: str) -> asyncio.Lock:
        """Return the lock that serialises site requests for one notebook.

        Studio does not say which request produced which site, so two site jobs for the same
        notebook must not overlap.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            The same Lock object for the same notebook.
        """
        locks: dict[str, asyncio.Lock] = self.__dict__.setdefault("_site_locks", {})
        if notebook_id not in locks:
            locks[notebook_id] = asyncio.Lock()
        return locks[notebook_id]

    @_translate_errors
    async def list_site_rows(self, notebook_id: str) -> list[SiteRow]:
        """List the learning sites in a notebook's Studio.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            Parsed site rows (any status).
        """
        async with self._client() as client:
            raw = await client.artifacts._list_raw(notebook_id)
        sites = [site for row in raw or [] if (site := parse_site_row(row)) is not None]
        logger.info("learning sites listed notebook=%s count=%d", notebook_id, len(sites))
        return sites

    @_translate_errors
    async def request_site(self, notebook_id: str, prompt: str, source_ids: list[str]) -> str:
        """Send the site prompt through chat with only the given sources ticked.

        Args:
            notebook_id: Notebook identifier.
            prompt: Prompt starting with `make me a site`.
            source_ids: Sources the site is built from.

        Returns:
            Gemini Notebook's chat answer text.
        """
        logger.info("learning site requested notebook=%s sources=%d", notebook_id, len(source_ids))
        async with self._client() as client:
            result = await client.chat.ask(notebook_id, prompt, source_ids=source_ids or None)
        return str(getattr(result, "answer", "") or "")

    def _site_http_client(self) -> httpx.AsyncClient:
        """Build the HTTP client carrying the saved Google cookies (tests override this).

        Returns:
            httpx.AsyncClient that never follows redirects by itself.
        """
        from notebooklm.auth import load_httpx_cookies

        cookies = load_httpx_cookies(path=self.storage_path)
        return httpx.AsyncClient(cookies=cookies, follow_redirects=False, timeout=120.0)

    async def download_site(self, row: SiteRow, output_path: str) -> None:
        """Download a finished site's HTML, following at most MAX_REDIRECTS Google-only redirects.

        Args:
            row: Finished site row.
            output_path: Local destination file.

        Raises:
            ValueError: When the URL or a redirect leaves Google, or the body is not HTML.
            AuthExpiredError: When Google answers with its sign-in page.
        """
        async with self._site_http_client() as http:
            url, response = await _follow_google_redirects(http, row.download_url)
        text = _check_site_body(url, response)
        _write_atomically(Path(output_path), text)
        logger.info("learning site downloaded id=%s bytes=%d", row.id, len(text.encode()))

"""Download one Google Fonts family (CSS + woff2 files) so the web page can use it offline (ADR-009).

Uses the public CSS2 API; the User-Agent asks for woff2. Every font file the CSS references is saved
next to a rewritten `font.css` that points at the local copies.
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.exceptions import FontDownloadError

logger = logging.getLogger(__name__)

CSS_URL = "https://fonts.googleapis.com/css2"
# A current desktop browser User-Agent: Google then serves woff2 files split by Unicode range.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)
FONT_URL = re.compile(r"url\((https://fonts\.gstatic\.com/[^)\s]+)\)")

HttpGet = Callable[[str, dict[str, str], float], bytes]


def urllib_get(url: str, headers: dict[str, str], timeout: float) -> bytes:
    """Fetch a URL with urllib.

    Args:
        url: URL to fetch.
        headers: Request headers.
        timeout: Timeout in seconds.

    Returns:
        Response body.

    Raises:
        FontDownloadError: On an HTTP error or a network failure.
    """
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https hosts
            body: bytes = response.read()
            return body
    except urllib.error.HTTPError as exc:
        raise FontDownloadError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FontDownloadError(f"network error: {exc}") from exc


class GoogleFontsClient:
    """Downloads Google Fonts families into a folder."""

    def __init__(
        self, get: HttpGet = urllib_get, max_bytes: int = 60 * 1024 * 1024, timeout: float = 30.0
    ) -> None:
        """Create the client.

        Args:
            get: Function that fetches a URL (replaced in tests).
            max_bytes: Largest total size of one family's font files.
            timeout: Timeout per request in seconds.
        """
        self.get = get
        self.max_bytes = max_bytes
        self.timeout = timeout

    def _css(self, family: str) -> str:
        """Fetch the family's CSS in weights 400 / 500 / 700, or its default weight when it lacks them.

        Args:
            family: Font family name, e.g. "LXGW WenKai TC".

        Returns:
            CSS text.

        Raises:
            FontDownloadError: The family does not exist or the request failed.
        """
        name = urllib.parse.quote_plus(family)
        headers = {"User-Agent": USER_AGENT}
        try:
            body = self.get(f"{CSS_URL}?family={name}:wght@400;500;700&display=swap", headers, self.timeout)
        except FontDownloadError:
            logger.info("Google Fonts: %s has no 400/500/700 set, trying its default weight", family)
            body = self.get(f"{CSS_URL}?family={name}&display=swap", headers, self.timeout)
        return body.decode("utf-8")

    def _save(self, url: str, path: Path) -> int:
        """Download one font file.

        Args:
            url: Font file URL on fonts.gstatic.com.
            path: Where to write it.

        Returns:
            Its size in bytes.
        """
        data = self.get(url, {"User-Agent": USER_AGENT}, self.timeout)
        path.write_bytes(data)
        return len(data)

    def download(self, family: str, dest: Path) -> dict[str, Any]:
        """Download a family into `dest` (font.css + numbered woff2 files).

        Args:
            family: Font family name.
            dest: Empty folder to write into.

        Returns:
            {"files": number of font files, "bytes": their total size}.

        Raises:
            FontDownloadError: Download failed, no font files were found, or the family is too large.
        """
        logger.info("Google Fonts: downloading %s", family)
        css = self._css(family)
        urls = list(dict.fromkeys(FONT_URL.findall(css)))
        if not urls:
            raise FontDownloadError(f"no font files found for {family!r}")
        dest.mkdir(parents=True, exist_ok=True)
        local = {url: f"{i:03d}.woff2" for i, url in enumerate(urls)}
        # Chinese families come in ~100-250 small files: fetch eight at a time
        with ThreadPoolExecutor(max_workers=8) as pool:
            sizes = list(pool.map(lambda url: self._save(url, dest / local[url]), urls))
        total = sum(sizes)
        if total > self.max_bytes:
            raise FontDownloadError(f"{family!r} is larger than {self.max_bytes // (1024 * 1024)} MB")
        css = FONT_URL.sub(lambda m: f'url("{local[m.group(1)]}")', css)
        (dest / "font.css").write_text(css, encoding="utf-8")
        logger.info("Google Fonts: saved %s (%d files, %d bytes)", family, len(urls), total)
        return {"files": len(urls), "bytes": total}

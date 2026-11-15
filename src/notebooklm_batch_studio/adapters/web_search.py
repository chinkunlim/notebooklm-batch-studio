"""Lightweight DuckDuckGo HTML web search adapter for optional Q&A supplementation."""

from __future__ import annotations

import asyncio
import html
import logging
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_RESULT_LINK_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.S,
)
_SNIPPET_RE = re.compile(r'class="result__snippet"[^>]*>(?P<snippet>.*?)</(?:a|div)>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(raw: str) -> str:
    """Remove HTML tags and collapse whitespace from an extracted fragment.

    Args:
        raw: Raw HTML fragment.

    Returns:
        Clean plain-text string.
    """
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub("", raw))).strip()


def _fetch_ddg_sync(query: str) -> str:
    """Synchronously POST a query to DuckDuckGo's HTML search endpoint.

    Args:
        query: Plain-text search query.

    Returns:
        Raw HTML response body.
    """
    payload = urlencode({"q": query}).encode("utf-8")
    req = Request(
        "https://html.duckduckgo.com/html/",
        data=payload,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NotebookLMBatchStudio/1.0)"},
        method="POST",
    )
    with urlopen(req, timeout=6.0) as resp:  # noqa: S310 - fixed HTTPS DuckDuckGo endpoint
        return str(resp.read().decode("utf-8", errors="replace"))


async def search_web_snippets(query: str, max_results: int = 4) -> list[dict[str, str]]:
    """Fetch top web search titles, URLs, and snippets via DuckDuckGo HTML endpoint.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.

    Returns:
        List of dicts with `title`, `url`, and `snippet` keys (empty on network failure).
    """
    cleaned = query.strip()
    if not cleaned:
        return []
    try:
        body = await asyncio.to_thread(_fetch_ddg_sync, cleaned)
    except Exception as exc:
        logger.warning("Web search unavailable for query %r: %s", cleaned[:60], exc)
        return []

    links = list(_RESULT_LINK_RE.finditer(body))
    snippets = [_strip_html(m.group("snippet")) for m in _SNIPPET_RE.finditer(body)]
    results: list[dict[str, str]] = []
    for idx, match in enumerate(links[:max_results]):
        title = _strip_html(match.group("title"))
        url = html.unescape(match.group("url"))
        snippet = snippets[idx] if idx < len(snippets) else ""
        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})
    return results

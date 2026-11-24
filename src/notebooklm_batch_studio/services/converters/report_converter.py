"""Render a Gemini Notebook report (Markdown) as a readable standalone HTML page.

The report text comes from Gemini Notebook, so raw HTML in it is escaped before Markdown rendering;
only Markdown formatting (headings, lists, tables, bold, quotes) becomes HTML. Link and image
URLs are then limited to safe schemes, because a prompt-injected source can make the model emit
`[x](javascript:...)` (Refs: ISSUE-013, ISSUE-046).
"""

from __future__ import annotations

import html
import logging
import re

import markdown

logger = logging.getLogger(__name__)

# Markdown-generated attributes that carry URLs (always double-quoted by Python-Markdown).
_URL_ATTR = re.compile(r'\b(href|src)="([^"]*)"')
# URL schemes allowed in rendered reports; anything else (javascript:, data:, vbscript:, ...) is dropped.
_SAFE_SCHEMES = ("http", "https", "mailto")
# Leading scheme of a URL, after control characters and whitespace are removed.
_SCHEME = re.compile(r"^([a-z][a-z0-9+.-]*):")

_STYLE = (
    "html{background:#0f172a;scrollbar-width:none;-ms-overflow-style:none;}"
    "html::-webkit-scrollbar,body::-webkit-scrollbar{display:none;}"
    "body{font-family:-apple-system,BlinkMacSystemFont,'PingFang TC','Noto Sans TC','Segoe UI',sans-serif;"
    "background:#0f172a;color:#e2e8f0;padding:32px 28px;line-height:1.8;max-width:960px;margin:0 auto;}"
    "h1,h2,h3,h4{color:#f8fafc;line-height:1.4;margin-top:1.6em;}h1{border-bottom:1px solid #334155;"
    "padding-bottom:.3em;}a{color:#38bdf8;}"
    "strong{color:#fde68a;}"
    "blockquote{border-left:4px solid #38bdf8;margin:1em 0;padding:.2em 1em;color:#cbd5e1;"
    "background:#1e293b;}"
    "table{border-collapse:collapse;width:100%;margin:1em 0;}th,td{border:1px solid #334155;padding:6px 10px;"
    "text-align:left;vertical-align:top;}th{background:#1e293b;}"
    "code{background:#1e293b;padding:1px 5px;border-radius:4px;}"
    "pre{background:#1e293b;padding:14px;border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere;}"
    "td,th{overflow-wrap:anywhere;}img{max-width:100%;}"
    "@media print{body{background:#fff;color:#111;}h1,h2,h3,h4,strong{color:#111;}th{background:#eee;}}"
)


def markdown_fragment(markdown_text: str) -> str:
    """Render Markdown to an HTML fragment, escaping any raw HTML in the source first.

    Args:
        markdown_text: Markdown from Gemini Notebook.

    Returns:
        HTML fragment (no page wrapper).
    """
    safe_source = markdown_text.replace("&", "&amp;").replace("<", "&lt;")
    rendered = markdown.markdown(safe_source, extensions=["tables", "sane_lists"])
    return _URL_ATTR.sub(_neutralize_url_attr, rendered)


def is_safe_url(raw_url: str) -> bool:
    """Tell whether a rendered link / image URL is relative or uses an allowed scheme.

    Args:
        raw_url: Attribute value as written in the HTML (may contain entities).

    Returns:
        True for relative URLs, fragments, and http / https / mailto URLs.
    """
    decoded = html.unescape(raw_url)
    compact = "".join(ch for ch in decoded if ch > " " and ch != "\x7f").lower()
    match = _SCHEME.match(compact)
    return match is None or match.group(1) in _SAFE_SCHEMES


def _neutralize_url_attr(match: re.Match[str]) -> str:
    """Replace an unsafe `href` / `src` value with `#`.

    Args:
        match: Regex match of one URL attribute.

    Returns:
        The original attribute, or the attribute pointing at `#` when its scheme is unsafe.
    """
    attr, value = match.group(1), match.group(2)
    if is_safe_url(value):
        return match.group(0)
    logger.warning("Dropped unsafe %s URL scheme in rendered Markdown", attr)
    return f'{attr}="#"'


def report_to_html(title: str, markdown_text: str) -> str:
    """Convert report Markdown into a styled HTML document.

    Args:
        title: Page title (escaped).
        markdown_text: Report content in Markdown, as downloaded from Gemini Notebook.

    Returns:
        Complete HTML document string.
    """
    body = markdown_fragment(markdown_text)
    safe_title = html.escape(title)
    return (
        '<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{safe_title}</title><style>{_STYLE}</style></head><body>{body}</body></html>"
    )

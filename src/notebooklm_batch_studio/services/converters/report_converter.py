"""Render a NotebookLM report (Markdown) as a readable standalone HTML page.

The report text comes from NotebookLM, so raw HTML in it is escaped before Markdown rendering;
only Markdown formatting (headings, lists, tables, bold, quotes) becomes HTML.
Refs: ISSUE-013
"""

from __future__ import annotations

import html

import markdown

_STYLE = (
    "body{font-family:-apple-system,BlinkMacSystemFont,'PingFang TC','Noto Sans TC','Segoe UI',sans-serif;"
    "background:#0f172a;color:#e2e8f0;padding:32px 20px;line-height:1.8;max-width:860px;margin:0 auto;}"
    "h1,h2,h3,h4{color:#f8fafc;line-height:1.4;margin-top:1.6em;}h1{border-bottom:1px solid #334155;"
    "padding-bottom:.3em;}a{color:#38bdf8;}"
    "strong{color:#fde68a;}"
    "blockquote{border-left:4px solid #38bdf8;margin:1em 0;padding:.2em 1em;color:#cbd5e1;"
    "background:#1e293b;}"
    "table{border-collapse:collapse;width:100%;margin:1em 0;}th,td{border:1px solid #334155;padding:6px 10px;"
    "text-align:left;vertical-align:top;}th{background:#1e293b;}"
    "code{background:#1e293b;padding:1px 5px;border-radius:4px;}"
    "pre{background:#1e293b;padding:14px;border-radius:8px;overflow-x:auto;}"
    "@media print{body{background:#fff;color:#111;}h1,h2,h3,h4,strong{color:#111;}th{background:#eee;}}"
)


def markdown_fragment(markdown_text: str) -> str:
    """Render Markdown to an HTML fragment, escaping any raw HTML in the source first.

    Args:
        markdown_text: Markdown from NotebookLM.

    Returns:
        HTML fragment (no page wrapper).
    """
    safe_source = markdown_text.replace("&", "&amp;").replace("<", "&lt;")
    return markdown.markdown(safe_source, extensions=["tables", "sane_lists"])


def report_to_html(title: str, markdown_text: str) -> str:
    """Convert report Markdown into a styled HTML document.

    Args:
        title: Page title (escaped).
        markdown_text: Report content in Markdown, as downloaded from NotebookLM.

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

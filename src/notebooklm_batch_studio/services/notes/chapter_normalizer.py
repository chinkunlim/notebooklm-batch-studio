"""Markdown normalizer for Gemini modular note outputs (Refs: ADR-012).

Cleans outer ```markdown fences, converts `[cite: ...]` into `(p. ...)`,
and normalizes legacy HTML underline tags back into semantic tags
(`{{定義:...}}`, `{{重要:...}}`, `{{清單:...}}`, `{{跨章:...}}`) so all
downstream layout metadata is preserved cleanly inside `.md` source files.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_RE_CITE = re.compile(r"\[cite:\s*([\d,\s]+)\]")
_RE_SOLID_U = re.compile(
    r'<u\s+style="[^"]*underline\s+solid\s+#2563eb[^"]*">(.*?)</u>',
    re.DOTALL | re.IGNORECASE,
)
_RE_WAVY_U = re.compile(
    r'<u\s+style="[^"]*underline\s+wavy\s+#dc2626[^"]*">(.*?)</u>',
    re.DOTALL | re.IGNORECASE,
)
_RE_DOUBLE_U = re.compile(
    r'<u\s+style="[^"]*underline\s+double\s+#d97706[^"]*">(.*?)</u>',
    re.DOTALL | re.IGNORECASE,
)
_RE_DASHED_U = re.compile(
    r'<u\s+style="[^"]*underline\s+dashed\s+#059669[^"]*">(.*?)</u>',
    re.DOTALL | re.IGNORECASE,
)


def normalize_semantic_markup(text: str) -> str:
    """Convert inline HTML underline tags back to semantic `{{...}}` markers.

    Args:
        text: Markdown text possibly containing HTML underline spans.

    Returns:
        Normalized Markdown preserving all semantic tags.
    """
    s = _RE_SOLID_U.sub(r"{{定義:\1}}", text)
    s = _RE_WAVY_U.sub(r"{{重要:\1}}", s)
    s = _RE_DOUBLE_U.sub(r"{{清單:\1}}", s)
    return _RE_DASHED_U.sub(r"{{跨章:\1}}", s)


def clean_cite_tags(text: str) -> str:
    """Convert `[cite: X, Y]` tags into `(p. X, Y)` and deduplicate adjacent page refs.

    Args:
        text: Raw Markdown output.

    Returns:
        Markdown with normalized page citations.
    """
    res = _RE_CITE.sub(r"(p. \1)", text)
    dup_code = re.compile(r"`\s*\(\s*pp?\.?\s*([\d\s–\-,]+)\s*\)\s*`\s*\(\s*pp?\.?\s*[\d\s–\-,]+\s*\)")
    dup_paren = re.compile(r"\(\s*pp?\.?\s*([\d\s–\-,]+)\s*\)\s*\(\s*pp?\.?\s*[\d\s–\-,]+\s*\)")
    for _ in range(3):
        res = dup_code.sub(r"(p. \1)", res)
        res = dup_paren.sub(r"(p. \1)", res)
    return res


def clean_markdown_fences(text: str) -> str:
    """Strip leading/trailing ```markdown wrappers and `<!-- END -->` markers.

    Args:
        text: Raw reply text from Gemini or NotebookLM.

    Returns:
        Clean inner Markdown preserving internal code fences (e.g. ```flowchart).
    """
    s = re.sub(r"\s*<!--\s*END\s*-->\s*$", "", text.strip()).strip()
    if not (s.startswith("```markdown") or s.startswith("```md")):
        return s
    first_nl = s.find("\n")
    if first_nl == -1:
        return s
    body = s[first_nl + 1 :].strip()
    m_end = re.search(r"\n```\s*$", body)
    if m_end and len(re.findall(r"^```", body, flags=re.MULTILINE)) % 2 == 1:
        return body[: m_end.start()].strip()
    return body


def normalize_step_markdown(text: str) -> str:
    """Run full Phase 1 normalization on a single module Markdown reply.

    Args:
        text: Raw Markdown reply from the LLM backend.

    Returns:
        Clean Markdown ready to save as `NN_<step>.md`.
    """
    cleaned = clean_markdown_fences(text)
    cleaned = clean_cite_tags(cleaned)
    return normalize_semantic_markup(cleaned).strip() + "\n"

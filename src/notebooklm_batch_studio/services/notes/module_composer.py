"""Modular Markdown chapter composer (Refs: ADR-012).

Stitches the 7 per-module Markdown files (`01_mindmap.md` .. `07_quiz.md`)
into a single clean chapter `.md` source note with YAML frontmatter, preserving
all semantic tags (`[核心]`, `{{定義:...}}`, `:::QEC`, etc.) for Phase 3 PDF rendering.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from notebooklm_batch_studio.domain.note_pipeline import STANDARD_NOTE_STEPS
from notebooklm_batch_studio.services.notes.chapter_normalizer import normalize_step_markdown

logger = logging.getLogger(__name__)

_RE_MODULE_HEADING = re.compile(r"^#\s*模組[一二三四五六七].*$", re.MULTILINE)
_RE_CHAPTER_NUM = re.compile(r"(\d+)")


def _extract_chapter_number(chapter_id: str) -> str:
    """Extract numeric chapter index from `ch01` or `01`.

    Args:
        chapter_id: Chapter identifier string.

    Returns:
        Numeric string such as `01`, or original `chapter_id` if no digits found.
    """
    match = _RE_CHAPTER_NUM.search(chapter_id)
    return match.group(1).zfill(2) if match else chapter_id


def _strip_leading_module_title(body: str) -> str:
    """Remove redundant `# 模組X：...` heading before inserting canonical section title.

    Args:
        body: Normalized module Markdown body.

    Returns:
        Body without duplicate top-level module heading.
    """
    return _RE_MODULE_HEADING.sub("", body, count=1).strip()


def compose_chapter_from_modules(
    chapter_dir: Path,
    chapter_id: str,
    chapter_title: str = "",
) -> str:
    """Stitch existing module `.md` files in `chapter_dir` into one chapter `.md`.

    Args:
        chapter_dir: Folder containing `01_mindmap.md` .. `07_quiz.md`.
        chapter_id: Chapter identifier (e.g. `ch01`).
        chapter_title: Human-readable chapter title.

    Returns:
        Complete stitched Markdown string with YAML frontmatter.

    Raises:
        FileNotFoundError: When `chapter_dir` does not exist.
    """
    if not chapter_dir.is_dir():
        raise FileNotFoundError(f"Chapter module directory not found: {chapter_dir}")

    ch_num = _extract_chapter_number(chapter_id)
    title_text = chapter_title or chapter_id
    frontmatter = f"---\nchapter: {ch_num}\ntitle: {title_text}\n---"
    sections: list[str] = [frontmatter]

    for step in STANDARD_NOTE_STEPS:
        mod_path = chapter_dir / f"{step.step_id}.md"
        if not mod_path.is_file():
            continue
        raw = mod_path.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        body = _strip_leading_module_title(normalize_step_markdown(raw))
        if body:
            sections.append(f"# {step.title}\n\n{body}")

    logger.debug("Composed %d sections from %s", len(sections) - 1, chapter_dir)
    return "\n\n---\n\n".join(sections) + "\n"

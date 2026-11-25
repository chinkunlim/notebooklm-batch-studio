"""Pure textbook chapter detection from PDF bookmarks (ported from literature-parser analyzer; SPEC-018)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# "Chapter 7 Groups", "1 Introduction …", "2. Ethics" — but not "1.1 Compare …" or "2024 Update".
_CHAPTER_RE = re.compile(r"^(?:chapter\s+)?(\d{1,3})(?!\d)(?!\.\d)(?:[\s.:\-–—]+(.*))?$", re.IGNORECASE)
# Same rule as literature-parser `sanitize_filename`, so names match chapters split there earlier.
_UNSAFE_CHARS = re.compile(r'[/\\:*?"<>|_,;&]+')
_MAX_TITLE_CHARS = 120
_MAX_TITLE_BYTES = 200
# Marks a `01 Materials/<book>/` folder as split textbook chapters (lecture source; SPEC-018).
TEXTBOOK_MARKER = ".textbook.json"


@dataclass(frozen=True)
class OutlineEntry:
    """One PDF bookmark.

    Attributes:
        level: Nesting depth starting at 1.
        title: Bookmark text.
        page: 1-based page number it points to.
    """

    level: int
    title: str
    page: int


@dataclass(frozen=True)
class PageRangeJob:
    """One chapter extraction request for the PDF adapter.

    Attributes:
        source: Textbook PDF.
        start: First page (1-based).
        end: Last page (inclusive).
        dest: Output chapter PDF.
        bookmarks: Chapter-relative bookmarks to keep.
    """

    source: Path
    start: int
    end: int
    dest: Path
    bookmarks: list[OutlineEntry] = field(default_factory=list)


def _clean_title(title: str) -> str:
    """Make a chapter title safe for file names (literature-parser `sanitize_filename` rule).

    Args:
        title: Raw chapter title.

    Returns:
        Hyphen-separated title, at most 120 characters / 200 UTF-8 bytes, possibly empty.
    """
    name = re.sub(r"[\x00-\x1f\x7f]+", "", title)
    name = re.sub(r"\s+", "-", _UNSAFE_CHARS.sub("-", name))
    name = re.sub(r"-+", "-", name).strip("-").rstrip(". ")
    if len(name) > _MAX_TITLE_CHARS:
        cut = name[:_MAX_TITLE_CHARS]
        if "-" in cut[_MAX_TITLE_CHARS // 2 :]:
            cut = cut.rsplit("-", 1)[0]
        name = cut.rstrip("- ")
    while len(name.encode("utf-8")) > _MAX_TITLE_BYTES and len(name) > 10:
        name = name[:-5].rstrip("- ")
    return name


def chapter_filename(number: int, title: str) -> str:
    """Build the `ChNN-Title.pdf` file name used for chapter PDFs.

    Args:
        number: Chapter number.
        title: Chapter title.

    Returns:
        File name; the title part follows `_clean_title`.
    """
    clean = _clean_title(title)
    return f"Ch{number:02d}-{clean}.pdf" if clean else f"Ch{number:02d}.pdf"


@dataclass(frozen=True)
class ChapterSection:
    """A detected chapter page range.

    Attributes:
        number: Chapter number.
        title: Chapter title without the number.
        start: First page (1-based).
        end: Last page (inclusive).
    """

    number: int
    title: str
    start: int
    end: int

    @property
    def pages(self) -> int:
        """Number of pages in the chapter.

        Returns:
            `end - start + 1`.
        """
        return self.end - self.start + 1

    @property
    def filename(self) -> str:
        """Chapter PDF file name.

        Returns:
            `ChNN-Title.pdf`.
        """
        return chapter_filename(self.number, self.title)


def _parse_chapter(title: str) -> tuple[int, str] | None:
    """Return `(number, title)` when a bookmark looks like a chapter heading.

    Args:
        title: Bookmark text.

    Returns:
        Parsed number and remaining title, or None.
    """
    match = _CHAPTER_RE.match(title.strip())
    if match is None:
        return None
    return int(match.group(1)), (match.group(2) or "").strip()


def _chapter_level(entries: list[OutlineEntry]) -> int | None:
    """Pick the outline level with the most chapter-like bookmarks (shallower wins ties).

    Args:
        entries: Flat outline in document order.

    Returns:
        Chosen level, or None when no bookmark looks like a chapter.
    """
    counts: dict[int, int] = {}
    for entry in entries:
        if _parse_chapter(entry.title) is not None:
            counts[entry.level] = counts.get(entry.level, 0) + 1
    if not counts:
        return None
    return min(counts, key=lambda level: (-counts[level], level))


def find_chapter_sections(entries: list[OutlineEntry], total_pages: int) -> list[ChapterSection]:
    """Detect chapter page ranges from a flat outline.

    Args:
        entries: Bookmarks in document order.
        total_pages: Page count of the book.

    Returns:
        Chapters in order; empty when no chapter bookmarks exist.
    """
    level = _chapter_level(entries)
    if level is None:
        return []
    sections: list[ChapterSection] = []
    seen: set[int] = set()
    for idx, entry in enumerate(entries):
        parsed = _parse_chapter(entry.title) if entry.level == level else None
        if parsed is None or parsed[0] in seen:
            continue
        nxt = [e.page for e in entries[idx + 1 :] if e.level <= level and e.page > entry.page]
        end = min(nxt[0] - 1, total_pages) if nxt else total_pages
        sections.append(ChapterSection(parsed[0], parsed[1], entry.page, max(end, entry.page)))
        seen.add(parsed[0])
    logger.debug("Detected %d chapters at outline level %d", len(sections), level)
    return sections

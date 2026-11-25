"""Which chapter folder a whole-book PDF splits into (Refs: ISSUE-072, SPEC-025 R3).

A course may already have chapter folders marked with `.textbook.json` (chapters moved from
`02 Handouts`, or an earlier split). With one such folder the book splits into it; with several, the
user chooses (the preview suggests the folder whose chapter files match the book's chapters best).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.path_safety import validate_path_segment
from notebooklm_batch_studio.domain.textbook_sections import TEXTBOOK_MARKER

logger = logging.getLogger(__name__)


def marked_folders(pdf: Path) -> list[Path]:
    """List chapter folders next to a textbook PDF (folders holding `.textbook.json`).

    Args:
        pdf: Textbook PDF in a materials folder.

    Returns:
        Marked folders, sorted by name.
    """
    return sorted(d for d in pdf.parent.iterdir() if d.is_dir() and (d / TEXTBOOK_MARKER).is_file())


def needs_choice(pdf: Path) -> bool:
    """Tell whether the user must pick the output folder.

    Args:
        pdf: Textbook PDF in a materials folder.

    Returns:
        True when the book has no own `<stem>/` folder and several marked folders exist.
    """
    return not (pdf.parent / pdf.stem).is_dir() and len(marked_folders(pdf)) > 1


def chapter_folder(pdf: Path, filenames: list[str] | None = None) -> Path:
    """Pick the default chapter folder for a whole-book PDF.

    The book's own `<stem>/` folder when it exists; else the only marked folder; with several marked
    folders, the one holding the most of `filenames` (if any match); otherwise a new `<stem>/` folder.

    Args:
        pdf: Textbook PDF in a materials folder.
        filenames: Chapter file names the book would produce, used to rank several marked folders.

    Returns:
        Chapter folder path (may not exist yet).
    """
    own = pdf.parent / pdf.stem
    marked = marked_folders(pdf)
    if own.is_dir() or not marked:
        return own
    if len(marked) == 1:
        return marked[0]
    wanted = set(filenames or [])
    scores = [(len(wanted & {p.name for p in d.glob("Ch*.pdf")}), d) for d in marked]
    best = max(score for score, _ in scores)
    winners = [d for score, d in scores if score == best]
    return winners[0] if best and len(winners) == 1 else own


def folder_choices(pdf: Path, course_dir: Path) -> list[dict[str, Any]]:
    """Describe the folders the user may choose from when a choice is needed.

    Args:
        pdf: Textbook PDF in a materials folder.
        course_dir: Course study directory.

    Returns:
        `[{path, name, chapters}]` (course-relative path, folder name, chapter PDF count); empty when
        no choice is needed.
    """
    if not needs_choice(pdf):
        return []
    return [
        {
            "path": d.relative_to(course_dir).as_posix(),
            "name": d.name,
            "chapters": sum(1 for _ in d.glob("Ch*.pdf")),
        }
        for d in marked_folders(pdf)
    ]


def chosen_folder(pdf: Path, name: str) -> Path:
    """Resolve the user's folder choice, accepting only an offered marked folder or the book's own folder.

    Args:
        pdf: Textbook PDF in a materials folder.
        name: Folder name inside the materials folder.

    Returns:
        Chapter folder path.

    Raises:
        ValueError: When `name` is not a single safe segment or not one of the allowed folders.
    """
    safe = validate_path_segment(name, "textbook folder")
    target = pdf.parent / safe
    if target in marked_folders(pdf) or target == pdf.parent / pdf.stem:
        return target
    logger.warning("Rejected textbook folder choice %r", name)
    raise ValueError(f"「{name}」不是這本課本可以選的輸出資料夾")

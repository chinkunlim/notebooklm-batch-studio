"""Read-only folder browser so the web app can pick course folders by clicking instead of typing.

A browser cannot hand a web page the absolute path of a local folder, so the local server lists
folders for it. Browsing is limited to the user's home directory and never reads file contents;
it only counts PDFs so the user can see which folder is a course.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SHORTCUT_NAMES = ("Desktop", "Documents", "Downloads")


def _pdf_count(folder: Path) -> int:
    """Count PDF files directly inside a folder.

    Args:
        folder: Folder to inspect.

    Returns:
        Number of `.pdf` files (0 when the folder cannot be read).
    """
    try:
        return sum(1 for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".pdf")
    except OSError:
        return 0


def _entry(folder: Path, label: str | None = None) -> dict[str, Any]:
    """Describe one folder for the picker.

    Args:
        folder: Folder path.
        label: Display name (defaults to the folder name).

    Returns:
        Dictionary with name, absolute path and PDF count.
    """
    return {"name": label or folder.name, "path": str(folder), "pdf_count": _pdf_count(folder)}


def browse_folders(path: str | None, courses_input_dir: Path, home: Path | None = None) -> dict[str, Any]:
    """List the sub-folders of a folder, or the starting shortcuts when no path is given.

    Args:
        path: Absolute folder path to open, or None for the shortcuts.
        courses_input_dir: The project's course input folder (first shortcut).
        home: Allowed root (defaults to the user's home directory; tests pass a temp folder).

    Returns:
        Dictionary with `path` (None for shortcuts), `parent` (None at the top), `pdf_count`
        and `folders` (name, path, pdf_count for each visible sub-folder, sorted by name).

    Raises:
        ValueError: When the path is outside the allowed root or is not a folder.
    """
    root = (home or Path.home()).resolve()
    if not path:
        shortcuts = (
            [_entry(courses_input_dir.resolve(), "課程資料夾 (input/courses)")]
            if courses_input_dir.is_dir()
            else []
        )
        shortcuts += [_entry(root / name) for name in SHORTCUT_NAMES if (root / name).is_dir()]
        return {"path": None, "parent": None, "pdf_count": 0, "folders": shortcuts}

    folder = Path(path).expanduser().resolve()
    if not folder.is_relative_to(root) or not folder.is_dir():
        raise ValueError(f"Folder not available: {path}")
    try:
        children = sorted(
            (c for c in folder.iterdir() if c.is_dir() and not c.name.startswith(".")),
            key=lambda c: c.name.lower(),
        )
    except OSError as err:
        raise ValueError(f"Folder cannot be read: {path}") from err
    parent = str(folder.parent) if folder != root and folder.parent.is_relative_to(root) else None
    logger.info("Browsing folder %s (%d sub-folders)", folder, len(children))
    return {
        "path": str(folder),
        "parent": parent,
        "pdf_count": _pdf_count(folder),
        "folders": [_entry(c) for c in children],
    }

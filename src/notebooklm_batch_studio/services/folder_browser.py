"""Read-only folder browser so the web app can pick course folders by clicking instead of typing.

A browser cannot hand a web page the absolute path of a local folder, so the local server lists
folders for it. Browsing is limited to the user's home directory and never reads file contents;
it only counts PDFs so the user can see which folder is a course.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig

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


def _shortcut_response(config: AppConfig, root: Path) -> dict[str, Any]:
    """Return top-level folder picker shortcuts.

    Args:
        config: Application configuration providing `study_root_dir`, `scratch_dir`, and legacy path.
        root: Allowed home root directory.

    Returns:
        Shortcut listing dictionary.
    """
    candidates = [
        (config.study_root_dir, "學習資料庫 (study)"),
        (config.scratch_dir, "未歸檔暫存 (scratch)"),
        (config.courses_input_dir, "舊課程資料夾（待整併）"),
    ]
    shortcuts = [_entry(folder.resolve(), label) for folder, label in candidates if folder.is_dir()]
    shortcuts += [_entry(root / name) for name in SHORTCUT_NAMES if (root / name).is_dir()]
    return {"path": None, "parent": None, "pdf_count": 0, "folders": shortcuts}


def _allowed_root(folder: Path, config: AppConfig, home: Path) -> Path | None:
    """Return the closest allowed root containing `folder` (home, study or scratch), or None.

    The study/scratch shortcuts must open even when DATA_DIR lives outside home (ISSUE-078);
    "up" navigation stops at the returned root.

    Args:
        folder: Resolved folder to open.
        config: Application configuration.
        home: Resolved home (or test) root.

    Returns:
        The deepest allowed root that contains `folder`, or None when none does.
    """
    roots = [home, config.study_root_dir.resolve(), config.scratch_dir.resolve()]
    allowed = [r for r in roots if folder.is_relative_to(r)]
    return max(allowed, key=lambda r: len(r.parts)) if allowed else None


def browse_folders(path: str | None, config: AppConfig, home: Path | None = None) -> dict[str, Any]:
    """List the sub-folders of a folder, or the starting shortcuts when no path is given.

    Args:
        path: Absolute folder path to open, or None for the shortcuts.
        config: Application configuration (first shortcuts are `study_root_dir` and `scratch_dir`).
        home: Allowed root (defaults to the user's home directory; tests pass a temp folder). The
            configured study and scratch folders are always allowed too.

    Returns:
        Dictionary with `path` (None for shortcuts), `parent` (None at the top), `pdf_count`
        and `folders` (name, path, pdf_count for each visible sub-folder, sorted by name).

    Raises:
        ValueError: When the path is outside the allowed roots or is not a folder.
    """
    root = (home or Path.home()).resolve()
    if not path:
        return _shortcut_response(config, root)

    folder = Path(path).expanduser().resolve()
    allowed = _allowed_root(folder, config, root)
    if allowed is None or not folder.is_dir():
        raise ValueError(f"Folder not available: {path}")
    root = allowed
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

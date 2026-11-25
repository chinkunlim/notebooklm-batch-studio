"""Browse every `.md` / `.pdf` inside a course NoteStudio folder, not only stitched chapters (SPEC-017)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.path_safety import ensure_within_roots
from notebooklm_batch_studio.services.notes.note_sync import list_chapter_notes

logger = logging.getLogger(__name__)

NOTE_FILE_SUFFIXES = (".md", ".pdf")
# Same exclusions as the legacy import: version history, prompt drafts, and PDF layout pages.
_EXCLUDED_DIRS = frozenset({"版本", "手動生成提示詞"})
_LAYOUT_PREFIX = ("學習筆記", "PDF", "layout")


def _is_listed(rel: Path) -> bool:
    """Tell whether a relative note path should appear in the file list.

    Args:
        rel: Path relative to the NoteStudio folder.

    Returns:
        True for visible `.md` / `.pdf` files outside excluded folders.
    """
    if rel.suffix.lower() not in NOTE_FILE_SUFFIXES or any(part.startswith(".") for part in rel.parts):
        return False
    if _EXCLUDED_DIRS.intersection(rel.parts[:-1]):
        return False
    return rel.parts[: len(_LAYOUT_PREFIX)] != _LAYOUT_PREFIX


def list_note_files(notes_dir: Path) -> list[dict[str, Any]]:
    """List note files recursively with their kind and whether they are stitched chapter notes.

    Args:
        notes_dir: Course NoteStudio directory.

    Returns:
        Sorted list of `{relative_path, kind, size, is_chapter}` dictionaries.
    """
    if not notes_dir.is_dir():
        return []
    chapter_paths = {Path(item["path"]).resolve() for item in list_chapter_notes(notes_dir)}
    files: list[dict[str, Any]] = []
    for path in sorted(notes_dir.rglob("*")):
        rel = path.relative_to(notes_dir)
        if path.is_symlink() or not path.is_file() or not _is_listed(rel):
            continue
        files.append(
            {
                "relative_path": rel.as_posix(),
                "kind": path.suffix.lower().lstrip("."),
                "size": path.stat().st_size,
                "is_chapter": path.resolve() in chapter_paths,
            }
        )
    return files


def resolve_note_file(notes_dir: Path, relative_path: str) -> Path:
    """Resolve a listed note file safely inside `notes_dir`.

    Args:
        notes_dir: Course NoteStudio directory.
        relative_path: Path relative to `notes_dir` (as returned by `list_note_files`).

    Returns:
        Absolute file path.

    Raises:
        PathSafetyError: When the path leaves `notes_dir`.
        FileNotFoundError: When the file does not exist or is not a listed note type.
    """
    target = ensure_within_roots(notes_dir / relative_path, [notes_dir], "note file")
    if target.is_symlink() or not target.is_file() or not _is_listed(target.relative_to(notes_dir.resolve())):
        raise FileNotFoundError(f"找不到筆記檔案：{relative_path}")
    return target


def read_note_file(notes_dir: Path, relative_path: str) -> dict[str, Any]:
    """Read a Markdown note, or report the path of a PDF note.

    Args:
        notes_dir: Course NoteStudio directory.
        relative_path: Path relative to `notes_dir`.

    Returns:
        `{relative_path, kind, path, content}`; `content` is empty for PDFs.
    """
    target = resolve_note_file(notes_dir, relative_path)
    kind = target.suffix.lower().lstrip(".")
    content = target.read_text(encoding="utf-8") if kind == "md" else ""
    logger.info("Read note file %s (%s)", relative_path, kind)
    return {"relative_path": relative_path, "kind": kind, "path": str(target), "content": content}

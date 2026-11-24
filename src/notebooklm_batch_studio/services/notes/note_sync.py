"""Phase 2 NoteStudio integration helpers: chapter listing, notebook push-back, and import."""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from notebooklm_batch_studio.services.converters.note_pdf_renderer import render_markdown_to_pdf

logger = logging.getLogger(__name__)

_RE_CHAPTER_STEM = re.compile(r"^(ch\d+)_(.+?)_學習筆記$", re.IGNORECASE)


def list_chapter_notes(notes_dir: Path) -> list[dict[str, Any]]:
    """List stitched chapter `.md` notes inside a NoteStudio directory.

    Args:
        notes_dir: Course NoteStudio directory (`03 Notes/NoteStudio` or `scratch/notes/<key>`).

    Returns:
        Sorted list of note metadata dictionaries.
    """
    if not notes_dir.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for md_path in sorted(notes_dir.glob("*_學習筆記.md")):
        match = _RE_CHAPTER_STEM.match(md_path.stem)
        chapter_id = match.group(1).lower() if match else md_path.stem
        title = match.group(2) if match else md_path.stem
        stat = md_path.stat()
        items.append(
            {
                "chapter_id": chapter_id,
                "title": title,
                "filename": md_path.name,
                "path": str(md_path),
                "size_bytes": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return items


def find_chapter_note(notes_dir: Path, chapter_id: str) -> Path:
    """Find the stitched `<chapter_id>_*_學習筆記.md` note for a chapter.

    Args:
        notes_dir: Course NoteStudio directory.
        chapter_id: Chapter identifier such as `ch01`.

    Returns:
        Path of the first matching note.

    Raises:
        FileNotFoundError: When no stitched note matches `chapter_id`.
    """
    matches = sorted(notes_dir.glob(f"{chapter_id}_*_學習筆記.md")) if notes_dir.is_dir() else []
    if not matches:
        raise FileNotFoundError(f"找不到 {chapter_id} 的縫合筆記 .md 檔案（{notes_dir}）。")
    return matches[0]


def push_chapter_note_to_source(
    notes_dir: Path,
    chapter_id: str,
    notebook_id: str,
    upload_fn: Callable[[str, str], str],
) -> dict[str, Any]:
    """Render a stitched chapter `.md` note to PDF and upload it to Gemini Notebook.

    Args:
        notes_dir: Course NoteStudio directory.
        chapter_id: Chapter identifier such as `ch01`.
        notebook_id: Target Gemini Notebook ID.
        upload_fn: Callback `(notebook_id, pdf_path) -> source_id`.

    Returns:
        Dictionary with `status`, `chapter_id`, `notebook_id`, `source_id`, and `pdf_path`.

    Raises:
        FileNotFoundError: When no stitched `.md` note matches `chapter_id`.
        ValueError: When `notebook_id` is empty.
    """
    if not notebook_id:
        raise ValueError("缺少目標 Gemini Notebook ID，無法推送至筆記本來源。")
    md_path = find_chapter_note(notes_dir, chapter_id)
    pdf_dir = notes_dir / "_uploaded"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{md_path.stem}.pdf"
    render_markdown_to_pdf(md_path.stem, md_path.read_text(encoding="utf-8"), pdf_path)
    source_id = upload_fn(notebook_id, str(pdf_path))
    logger.info("Pushed NoteStudio chapter %s to notebook=%s source=%s", chapter_id, notebook_id, source_id)
    return {
        "status": "uploaded",
        "chapter_id": chapter_id,
        "notebook_id": notebook_id,
        "source_id": source_id,
        "pdf_path": str(pdf_path),
        "md_path": str(md_path),
    }


def list_legacy_markdown_files(source_dir: Path) -> list[Path]:
    """Return sorted relative paths of non-hidden, non-symlink `.md` files under `source_dir`.

    Args:
        source_dir: Root directory of legacy NoteStudio outputs.

    Returns:
        Sorted list of relative `.md` paths inside `source_dir`.
    """
    if not source_dir.is_dir():
        return []
    results: list[Path] = []
    for path in sorted(source_dir.rglob("*.md")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(source_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        results.append(rel)
    return results


def import_legacy_notes(
    source_dir: Path,
    target_notes_dir: Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Copy existing `.md` notes recursively from standalone `note-studio` into `03 Notes/NoteStudio`.

    Args:
        source_dir: Source folder containing `.md` notes (flat or nested subdirectories).
        target_notes_dir: Destination `03 Notes/NoteStudio` directory.
        overwrite: Whether to overwrite existing files at the same relative path.

    Returns:
        Summary dictionary with `copied`, `skipped`, and `target_dir`.

    Raises:
        FileNotFoundError: When `source_dir` does not exist.
    """
    if not source_dir.is_dir():
        raise FileNotFoundError(f"找不到來源筆記資料夾：{source_dir}")
    target_notes_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    skipped: list[str] = []
    for rel in list_legacy_markdown_files(source_dir):
        src = source_dir / rel
        dst = target_notes_dir / rel
        if dst.exists() and not overwrite:
            skipped.append(rel.as_posix())
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel.as_posix())
    logger.info(
        "Imported %d legacy .md notes into %s (skipped %d)", len(copied), target_notes_dir, len(skipped)
    )
    return {
        "target_dir": str(target_notes_dir),
        "copied": copied,
        "skipped": skipped,
    }

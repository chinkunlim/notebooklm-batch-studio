"""Filesystem, inventory, and step-execution helpers for legacy consolidation (Refs: SPEC-014, ADR-015)."""

from __future__ import annotations

import json
import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from notebooklm_batch_studio.config.study_layout import CategoryRole, StudyLayout
from notebooklm_batch_studio.domain.course_identity import parse_course_folder

logger = logging.getLogger(__name__)

ActionType = Literal["move", "copy", "merge", "rename_code", "rename_folder", "import_notes", "inventory"]


@dataclass(frozen=True)
class ConsolidationStep:
    """One planned or executed consolidation action item."""

    action: ActionType
    source: str
    target: str
    note: str


@dataclass(frozen=True)
class ConsolidationRequest:
    """User-supplied mappings for planning legacy consolidation."""

    code_maps: dict[str, str] = field(default_factory=dict)
    folder_maps: dict[str, str] = field(default_factory=dict)
    assignments: list[tuple[str, str, CategoryRole, str]] = field(default_factory=list)
    restores: list[tuple[str, str, CategoryRole, str]] = field(default_factory=list)
    note_course_maps: dict[str, str] = field(default_factory=dict)


MANAGED_DATA_DIRS = frozenset(
    {
        "db",
        "logs",
        "state",
        "input",
        "output",
        "needs_review",
        "study",
        "scratch",
        "deleted",
        "tmp",
        "diagnostics",
        "fonts",
        "prompts",
    }
)


def unique_dest_path(dst: Path) -> Path:
    """Return `dst` if free, else append `_1`, `_2`, ... before suffix without overwriting.

    Args:
        dst: Desired destination file path.

    Returns:
        Unused `Path` safe to move/copy into.
    """
    if not dst.exists():
        return dst
    idx = 1
    while True:
        candidate = dst.with_name(f"{dst.stem}_{idx}{dst.suffix}")
        if not candidate.exists():
            return candidate
        idx += 1


def _transfer_dir_non_overwriting(
    src_dir: Path, dst_dir: Path, transfer_fn: Callable[[str, str], object]
) -> list[tuple[str, str]]:
    """Move or copy non-hidden files from `src_dir` into `dst_dir` without overwriting.

    Args:
        src_dir: Source directory path.
        dst_dir: Destination directory path.
        transfer_fn: File transfer function taking `(src_str, dst_str)` (`shutil.move` or `shutil.copy2`).

    Returns:
        List of `(old_relative_str, new_relative_str)` pairs for every transferred file.
    """
    if not src_dir.is_dir():
        return []
    transferred: list[tuple[str, str]] = []
    for src_file in sorted(src_dir.rglob("*")):
        if not src_file.is_file() or src_file.is_symlink() or src_file.name.startswith("."):
            continue
        rel = src_file.relative_to(src_dir)
        target = unique_dest_path(dst_dir / rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        transfer_fn(str(src_file), str(target))
        transferred.append((str(rel), str(target.relative_to(dst_dir))))
    return transferred


def merge_directory_non_overwriting(src_dir: Path, dst_dir: Path) -> list[tuple[str, str]]:
    """Move non-hidden files from `src_dir` into `dst_dir` without overwriting or deleting empty dirs.

    Args:
        src_dir: Source directory (e.g. legacy singular folder).
        dst_dir: Destination directory (e.g. canonical plural folder).

    Returns:
        List of `(old_relative_str, new_relative_str)` pairs for every moved file.
    """
    moved = _transfer_dir_non_overwriting(src_dir, dst_dir, shutil.move)
    logger.info("Merged %d files from %s into %s", len(moved), src_dir, dst_dir)
    return moved


def singular_aliases_for(layout: StudyLayout, role: CategoryRole) -> tuple[str, ...]:
    """Collect configured read aliases plus trailing-s singular directory names for `role`.

    Args:
        layout: Active `StudyLayout` configuration.
        role: Semantic category role.

    Returns:
        Ordered deduplicated tuple of alias names distinct from the primary name.
    """
    primary = layout.names[role]
    candidates = list(layout.aliases.get(role, ()))
    if primary.endswith("s") and len(primary) > 1:
        candidates.append(primary[:-1])
    seen: list[str] = []
    for name in candidates:
        if name != primary and name not in seen:
            seen.append(name)
    return tuple(seen)


def _rewrite_prefix(raw: str, prefixes: tuple[str, ...], new_dir: str) -> str | None:
    """Replace `prefixes` in `raw` with `new_dir` when equal or subpath (handling OS symlinks).

    Args:
        raw: Original path string.
        prefixes: Matching old prefix strings (raw and resolved).
        new_dir: Replacement prefix directory string.

    Returns:
        Updated string if matched, otherwise None.
    """
    for candidate in dict.fromkeys([raw, os.path.realpath(raw)]):
        for prefix in prefixes:
            if candidate == prefix:
                return new_dir
            if candidate.startswith(prefix + os.sep):
                return f"{new_dir}{candidate[len(prefix) :]}"
    return None


def rewrite_notes_state_folder_paths(
    notes_state_dir: Path, old_dir: str, new_dir: str
) -> list[tuple[Path, str]]:
    """Rewrite NoteStudio `stitched_path` entries matching `old_dir` across state JSON files.

    Args:
        notes_state_dir: Directory storing `<course_key>.json` NoteStudio states.
        old_dir: Old course study directory string.
        new_dir: New course study directory string.

    Returns:
        List of `(file_path, original_json_text)` backups for rollback on failure.
    """
    if not notes_state_dir.is_dir():
        return []
    prefixes = tuple(dict.fromkeys([str(Path(old_dir)), str(Path(old_dir).resolve())]))
    backups: list[tuple[Path, str]] = []
    for state_file in sorted(notes_state_dir.glob("*.json")):
        if state_file.name.endswith(".pause.json"):
            continue
        raw_text = state_file.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
        if _rewrite_payload_chapters(payload, prefixes, new_dir):
            backups.append((state_file, raw_text))
            state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return backups


def _rewrite_payload_chapters(payload: object, prefixes: tuple[str, ...], new_dir: str) -> bool:
    """Mutate matching `chapters.*.stitched_path` entries inside parsed state payload.

    Args:
        payload: Parsed JSON dictionary.
        prefixes: Matching old folder prefixes.
        new_dir: Replacement folder prefix.

    Returns:
        True if at least one `stitched_path` changed.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("chapters"), dict):
        return False
    changed = False
    for chapter in payload["chapters"].values():
        if not isinstance(chapter, dict) or not isinstance(chapter.get("stitched_path"), str):
            continue
        updated = _rewrite_prefix(chapter["stitched_path"], prefixes, new_dir)
        if updated is not None and updated != chapter["stitched_path"]:
            chapter["stitched_path"] = updated
            changed = True
    return changed


def restore_notes_state_backups(backups: list[tuple[Path, str]]) -> None:
    """Restore pre-rename JSON text for NoteStudio state files during rollback.

    Args:
        backups: Sequence of `(state_file_path, original_text)` recorded before writing.
    """
    for path, raw_text in backups:
        path.write_text(raw_text, encoding="utf-8")


def has_running_note_state(notes_state_dir: Path) -> bool:
    """Return True when any NoteStudio course state JSON marks a chapter or run as `running`.

    Args:
        notes_state_dir: Directory containing NoteStudio state JSON files.

    Returns:
        True when any note generation job is active.
    """
    if not notes_state_dir.is_dir():
        return False
    for state_file in sorted(notes_state_dir.glob("*.json")):
        if state_file.name.endswith(".pause.json"):
            continue
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        chapters = payload.get("chapters", {})
        if payload.get("status") == "running" or (
            isinstance(chapters, dict)
            and any(isinstance(ch, dict) and ch.get("status") == "running" for ch in chapters.values())
        ):
            return True
    return False


def inventory_directory_summary(folder: Path) -> str:
    """Compute a read-only summary string (files, MB, modified date, learning artifacts).

    Args:
        folder: Directory to summarize without modifying or copying files.

    Returns:
        Compact summary string covering counts, size, date, and extension breakdown.
    """
    total_bytes, file_count = 0, 0
    ext_counts: dict[str, int] = {}
    for root, _dirs, files in os.walk(folder, followlinks=False):
        for fname in files:
            fpath = Path(root) / fname
            if fpath.is_symlink() or fname.startswith("."):
                continue
            file_count += 1
            total_bytes += fpath.stat().st_size
            ext = fpath.suffix.lower() or "(no-ext)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
    mtime_iso = datetime.fromtimestamp(folder.stat().st_mtime, tz=UTC).strftime("%Y-%m-%d")
    has_learning = any(k in ext_counts for k in (".json", ".md", ".pdf"))
    ext_str = ", ".join(f"{k}:{v}" for k, v in sorted(ext_counts.items())) or "empty"
    return (
        f"size={total_bytes}B ({total_bytes / (1024 * 1024):.2f}MB) | date={mtime_iso} | "
        f"files={file_count} | has_learning_data={has_learning} | ext=[{ext_str}]"
    )


def _scan_loose_data_dirs(data_dir: Path, assigned_paths: set[Path]) -> list[tuple[str, str, str]]:
    """Collect inventory rows for unexpected loose top-level directories in `DATA_DIR`.

    Args:
        data_dir: Configured `DATA_DIR`.
        assigned_paths: Paths already explicitly assigned via `--assign`.

    Returns:
        List of `(source, target, note)` inventory tuples.
    """
    if not data_dir.is_dir():
        return []
    rows: list[tuple[str, str, str]] = []
    for entry in sorted(data_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name in MANAGED_DATA_DIRS:
            continue
        if entry.resolve() in assigned_paths:
            continue
        rows.append(
            (str(entry), "(DATA_DIR 散落資料夾，待 --assign 指派)", inventory_directory_summary(entry))
        )
    return rows


def _scan_nonstandard_study(study_root: Path, mapped_folders: set[str]) -> list[tuple[str, str, str]]:
    """Collect inventory rows for `study/<term>/<folder>` dirs lacking school numbering.

    Args:
        study_root: Configured `study/` directory.
        mapped_folders: Folder paths/names already targeted by `--folder`.

    Returns:
        List of `(source, target, note)` inventory tuples.
    """
    if not study_root.is_dir():
        return []
    rows: list[tuple[str, str, str]] = []
    for term_dir in sorted(study_root.iterdir()):
        if not term_dir.is_dir() or term_dir.name.startswith("."):
            continue
        rows.extend(_scan_term_nonstandard_dirs(term_dir, mapped_folders))
    return rows


def _scan_term_nonstandard_dirs(term_dir: Path, mapped_folders: set[str]) -> list[tuple[str, str, str]]:
    """Scan one semester directory inside `study/` for non-standard course folders.

    Args:
        term_dir: Term directory path.
        mapped_folders: Folder paths/names already handled by `--folder`.

    Returns:
        List of `(source, target, note)` inventory tuples.
    """
    rows: list[tuple[str, str, str]] = []
    for cdir in sorted(term_dir.iterdir()):
        if not cdir.is_dir() or cdir.name.startswith("."):
            continue
        if str(cdir.resolve()) in mapped_folders or cdir.name in mapped_folders:
            continue
        parsed = parse_course_folder(cdir.name)
        if parsed is None or not parsed.course_no:
            rows.append(
                (str(cdir), "(非校方命名資料夾，可用 --folder 改名)", inventory_directory_summary(cdir))
            )
    return rows


def collect_inventory_rows(
    data_dir: Path,
    study_root: Path,
    deleted_dir: Path,
    skip_sets: tuple[set[Path], set[str]],
) -> list[tuple[str, str, str]]:
    """Collect read-only `(source, target, note)` inventory rows across data, study, and deleted dirs.

    Args:
        data_dir: Configured `DATA_DIR`.
        study_root: Configured `study/` root.
        deleted_dir: Configured `deleted/` root.
        skip_sets: Tuple of `(assigned_paths, mapped_folder_keys)` already covered by actions.

    Returns:
        List of `(source, target, note)` inventory tuples.
    """
    assigned_paths, mapped_folders = skip_sets
    rows = _scan_loose_data_dirs(data_dir, assigned_paths)
    rows.extend(_scan_nonstandard_study(study_root, mapped_folders))
    if not deleted_dir.is_dir():
        return rows
    for entry in sorted(deleted_dir.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            rows.append((str(entry), "(deleted 只清點不搬不刪)", inventory_directory_summary(entry)))
    return rows


def apply_folder_rename_step(notes_state_dir: Path, repo: Any, source: str, target: str) -> None:
    """Atomically rename a study folder, NoteStudio state `stitched_path`s, and DB rows.

    Args:
        notes_state_dir: Directory containing NoteStudio state JSON files.
        repo: Active consolidation repository supporting rewrite/commit/rollback.
        source: Existing course folder path string.
        target: Destination school-formatted folder path string.
    """
    src_dir, dst_dir = Path(source), Path(target)
    if not src_dir.is_dir():
        raise FileNotFoundError(f"找不到要改名的課程資料夾：{src_dir}")
    if dst_dir.exists():
        raise FileExistsError(f"目標課程資料夾已存在，拒絕覆寫：{dst_dir}")
    parsed = parse_course_folder(dst_dir.name)
    # Refs: ISSUE-069 — subject is the course title (e.g. 生涯諮商與實務), not the `CP__31000-…` folder name.
    meta: dict[str, str] = {"subject": parsed.name if parsed and parsed.is_course else dst_dir.name}
    if parsed and parsed.course_no:
        meta["course_no"] = parsed.course_no
    dst_dir.parent.mkdir(parents=True, exist_ok=True)
    moved, state_backups = False, []
    try:
        shutil.move(str(src_dir), str(dst_dir))
        moved = True
        state_backups = rewrite_notes_state_folder_paths(notes_state_dir, str(src_dir), str(dst_dir))
        repo.rewrite_course_folder_paths(str(src_dir), str(dst_dir), meta=meta)
        repo.commit()
    except Exception:
        repo.rollback()
        restore_notes_state_backups(state_backups)
        if moved and dst_dir.exists() and not src_dir.exists():
            shutil.move(str(dst_dir), str(src_dir))
        raise


def apply_merge_step(repo: Any, source: str, target: str) -> None:
    """Merge a singular category directory into its plural target and sync DB category names.

    Args:
        repo: Consolidation repository.
        source: Source singular directory path string.
        target: Target plural directory path string.
    """
    src_dir, dst_dir = Path(source), Path(target)
    moved = merge_directory_non_overwriting(src_dir, dst_dir)
    if not moved and not src_dir.is_dir():
        return
    course_dir = str(dst_dir.parent.resolve())
    matched_code = next(
        (
            c.code
            for c in repo.list_courses()
            if c.study_dir and str(Path(c.study_dir).resolve()) == course_dir
        ),
        None,
    )
    repo.rewrite_category_name(src_dir.name, dst_dir.name, course_code=matched_code)
    if not matched_code:
        repo.commit()
        return
    for old_rel, new_rel in moved:
        if old_rel != new_rel:
            repo.update_lecture_relative_path(
                matched_code, f"{src_dir.name}/{old_rel}", f"{dst_dir.name}/{new_rel}"
            )
    repo.commit()


def _apply_transfer_step(
    source: str, target: str, transfer_fn: Callable[[str, str], object], label: str
) -> None:
    """Move or copy a file or directory cleanly into `target` without overwriting existing files.

    Args:
        source: Source file or folder path string.
        target: Destination file or directory path string.
        transfer_fn: `shutil.move` or `shutil.copy2`.
        label: Chinese verb used in error messages (`搬移` or `複製`).

    Raises:
        FileNotFoundError: When `source` does not exist.
    """
    src, dst = Path(source), Path(target)
    if src.is_dir():
        _transfer_dir_non_overwriting(src, dst, transfer_fn)
        return
    if not src.is_file():
        raise FileNotFoundError(f"找不到要{label}的檔案：{src}")
    candidate = (dst / src.name) if dst.is_dir() else dst
    final_dst = unique_dest_path(candidate)
    final_dst.parent.mkdir(parents=True, exist_ok=True)
    transfer_fn(str(src), str(final_dst))


def apply_move_step(source: str, target: str) -> None:
    """Move a file or directory cleanly into `target` without overwriting existing files.

    Args:
        source: Source file or folder path string.
        target: Destination file or directory path string.
    """
    _apply_transfer_step(source, target, shutil.move, "搬移")


def apply_copy_step(source: str, target: str) -> None:
    """Copy a file or directory cleanly into `target` without overwriting or deleting source files.

    Args:
        source: Source file or folder path string (e.g. inside `deleted/`).
        target: Destination file or directory path string.
    """
    _apply_transfer_step(source, target, shutil.copy2, "複製")

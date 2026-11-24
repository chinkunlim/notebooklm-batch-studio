"""Task 11b rename helpers: active-lock guards, legacy/needs_review moves, stitched_path rewrites."""

from __future__ import annotations

import errno
import fcntl
import json
import logging
import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.domain.study_hierarchy import resolve_course_output_root

logger = logging.getLogger(__name__)


def _safe_key(name: str) -> str:
    """Return filesystem-safe filename stem matching `NoteStateManager`.

    Args:
        name: Raw course code.

    Returns:
        Sanitized stem.
    """
    cleaned = re.sub(r"[^\w\-.]+", "_", name.strip()).lstrip(".")
    return cleaned or "default"


def _is_flock_held(lock_path: Path) -> bool:
    """Return True if another open file descriptor currently holds an exclusive flock on `lock_path`.

    Args:
        lock_path: OS lock file path.

    Returns:
        True when `LOCK_EX | LOCK_NB` raises `EAGAIN` or `EACCES`.
    """
    if not lock_path.exists():
        return False
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return True
        raise
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def check_active_locks(config: AppConfig, old_code: str, linked_lit_count: int) -> None:
    """Refuse rename when note generation for `old_code` is running or linked literature lock is held.

    Args:
        config: Application configuration.
        old_code: Source course code.
        linked_lit_count: Number of `literature_items` linked to `old_code`.

    Raises:
        ValueError: When active note generation or locked linked literature run is detected.
    """
    state_path = config.notes_state_dir / f"{_safe_key(old_code)}.json"
    if state_path.is_file():
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        chapters = payload.get("chapters", {}) if isinstance(payload, dict) else {}
        note_running = (isinstance(payload, dict) and payload.get("status") == "running") or any(
            isinstance(ch, dict) and ch.get("status") == "running" for ch in chapters.values()
        )
        if note_running:
            raise ValueError(f"課程 {old_code} 有筆記生成執行中，無法更改代碼")
    if linked_lit_count > 0 and _is_flock_held(config.literature_job_lock_path):
        raise ValueError(f"文獻任務執行中且課程 {old_code} 含關聯文獻，無法更改代碼")


def rewrite_stitched_path(raw_path: str, old_code: str, new_code: str, scratch_root: Path) -> str:
    """Rewrite note `stitched_path` when it points under `scratch/notes/<old_code>/` (Refs: ISSUE-067).

    Args:
        raw_path: Stored `stitched_path` value (absolute or relative).
        old_code: Previous course code.
        new_code: Replacement course code.
        scratch_root: `config.scratch_kind_dir("notes")` root folder.

    Returns:
        Rewritten path string when referencing scratch notes; unchanged otherwise (e.g. `study_dir`).
    """
    if raw_path == old_code or raw_path.startswith(f"{old_code}/"):
        return f"{new_code}{raw_path[len(old_code) :]}"
    old_dir, new_dir = scratch_root / old_code, scratch_root / new_code
    candidate = Path(raw_path)
    for base_old, base_new in ((old_dir, new_dir), (old_dir.resolve(), new_dir)):
        if candidate.is_relative_to(base_old):
            return str(base_new / candidate.relative_to(base_old))
        resolved = candidate.resolve()
        if resolved.is_relative_to(base_old):
            return str(base_new / resolved.relative_to(base_old))
    return raw_path


def collect_state_pairs(notes_state_dir: Path, old_code: str, new_code: str) -> list[tuple[Path, Path]]:
    """Collect existing `.json` and `.pause.json` note state file pairs for `old_code` -> `new_code`.

    Args:
        notes_state_dir: Directory holding note state JSON files.
        old_code: Current course code.
        new_code: Replacement course code.

    Returns:
        List of `(src_path, dst_path)` pairs for files present on disk.
    """
    old_key, new_key = _safe_key(old_code), _safe_key(new_code)
    pairs: list[tuple[Path, Path]] = []
    for ext in (".json", ".pause.json"):
        src = notes_state_dir / f"{old_key}{ext}"
        if src.is_file():
            pairs.append((src, notes_state_dir / f"{new_key}{ext}"))
    return pairs


def build_rename_target_bundle(
    parts: dict[str, Any],
) -> dict[str, Any]:
    """Assemble target bundle dictionary and summary counts for dry-run and apply steps.

    Args:
        parts: Intermediate discovered paths (`toml`, `state_files`, `scratch_src`, `scratch_dst`,
            `output_pairs`, `review_pairs`, `qa_files`).

    Returns:
        Normalized targets dictionary including nested `counts`.
    """
    return {
        **parts,
        "counts": {
            "course_toml": 1 if parts["toml"] is not None else 0,
            "notes_state": len(parts["state_files"]),
            "scratch_notes": 1 if parts["scratch_src"] is not None else 0,
            "course_output": len(parts["output_pairs"]),
            "needs_review": len(parts["review_pairs"]),
            "qa_notes": len(parts["qa_files"]),
        },
    }


def rewrite_migrated_state_stitched_paths(
    state_files: list[tuple[Path, Path]], old_code: str, new_code: str, scratch_root: Path
) -> None:
    """Update scratch `stitched_path` entries inside already-migrated note state JSON files.

    Args:
        state_files: Migrated `(src, dst)` pairs whose `dst` files were just written.
        old_code: Previous course code.
        new_code: Replacement course code.
        scratch_root: `config.scratch_kind_dir("notes")` root directory.
    """
    for _src, dst in state_files:
        if not dst.is_file():
            continue
        payload = json.loads(dst.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            rewrite_chapter_stitched_paths(payload, old_code, new_code, scratch_root)
            dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def rewrite_chapter_stitched_paths(
    payload: dict[str, Any], old_code: str, new_code: str, scratch_root: Path
) -> None:
    """Update scratch-backed chapter `stitched_path` entries inside parsed note-state JSON.

    Args:
        payload: Mutable parsed note state dictionary.
        old_code: Previous course code.
        new_code: Replacement course code.
        scratch_root: `config.scratch_kind_dir("notes")` root folder.
    """
    chapters = payload.get("chapters")
    if not isinstance(chapters, dict):
        return
    for ch in chapters.values():
        if isinstance(ch, dict) and isinstance(ch.get("stitched_path"), str):
            ch["stitched_path"] = rewrite_stitched_path(ch["stitched_path"], old_code, new_code, scratch_root)


def collect_legacy_and_review_pairs(
    config: AppConfig, course: Course, old_code: str, new_code: str
) -> tuple[list[tuple[Path, Path]], list[tuple[Path, Path]]]:
    """Collect fallback `output/courses/<old>` and `needs_review/<old>_*` directory rename pairs.

    Args:
        config: Application configuration.
        course: Loaded `Course` domain entity.
        old_code: Current course code.
        new_code: Replacement course code.

    Returns:
        `(output_pairs, review_pairs)` tuples validated against destination collisions.
    """
    output_pairs: list[tuple[Path, Path]] = []
    if not course.study_dir:
        old_out = resolve_course_output_root(config.courses_output_dir, old_code, "")
        if old_out.is_dir():
            output_pairs.append(
                (old_out, resolve_course_output_root(config.courses_output_dir, new_code, ""))
            )
    review_pairs: list[tuple[Path, Path]] = []
    if config.needs_review_dir.is_dir():
        prefix = f"{old_code}_"
        review_pairs = [
            (src, config.needs_review_dir / f"{new_code}_{src.name.removeprefix(prefix)}")
            for src in sorted(config.needs_review_dir.glob(f"{old_code}_*"))
            if src.is_dir()
        ]
    for _src, dst in (*output_pairs, *review_pairs):
        if dst.exists():
            raise ValueError(f"目標資料夾已存在：{dst}")
    return output_pairs, review_pairs


def build_path_rewrites(targets: dict[str, Any]) -> list[tuple[str, str]]:
    """Compute `(old_prefix, new_prefix)` directory prefix pairs for `artifact_jobs.output_file`.

    Args:
        targets: Collected filesystem targets dictionary.

    Returns:
        List of `(str(old_dir), str(new_dir))` pairs.
    """
    pairs = (*targets.get("output_pairs", ()), *targets.get("review_pairs", ()))
    return [(str(src), str(dst)) for src, dst in pairs]


def _restore_dir(src: Path, dst: Path) -> Callable[[], None]:
    """Build typed rollback callable moving `dst` back to `src`.

    Args:
        src: Original directory path.
        dst: Destination directory path created by move.

    Returns:
        Zero-argument rollback callable.
    """

    def _undo() -> None:
        """Restore moved directory back to source location."""
        if dst.exists():
            shutil.move(str(dst), str(src))

    return _undo


def move_dir_pairs(pairs: list[tuple[Path, Path]], undo: list[Callable[[], None]], label: str) -> int:
    """Move each `(src, dst)` directory pair after verifying destination does not collide.

    Args:
        pairs: Sequence of `(source_dir, dest_dir)` pairs.
        undo: Rollback callback stack.
        label: Human-readable folder category label for conflict errors.

    Returns:
        Number of moved directories.
    """
    for _src, dst in pairs:
        if dst.exists():
            raise ValueError(f"{label}目標資料夾已存在：{dst}")
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        undo.append(_restore_dir(src, dst))
    return len(pairs)

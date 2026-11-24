"""Course lifecycle service: archive, restore, and transactional safe course-code rename (Refs: SPEC-014)."""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course, CourseStatus
from notebooklm_batch_studio.domain.path_safety import validate_path_segment
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol, QueueRepositoryProtocol
from notebooklm_batch_studio.domain.study_layout import CategoryRole
from notebooklm_batch_studio.services.course_rename_files import (
    build_path_rewrites,
    build_rename_target_bundle,
    check_active_locks,
    collect_legacy_and_review_pairs,
    collect_state_pairs,
    move_dir_pairs,
    rewrite_migrated_state_stitched_paths,
)

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"\A(---\r?\n)(.*?)(\r?\n---(?:\r?\n|\Z))", re.DOTALL)


class CourseIdentityRepositoryProtocol(Protocol):
    """Transactional DB identity repository contract for safe course-code renames."""

    def preview_rename(self, old_code: str, new_code: str) -> dict[str, int]:
        """Count affected rows for a proposed rename.

        Args:
            old_code: Current course code.
            new_code: Proposed replacement course code.

        Returns:
            Table-name to affected row-count mapping.
        """
        ...

    def rename_code(
        self,
        old_code: str,
        new_code: str,
        *,
        commit: bool = True,
        path_rewrites: list[tuple[str, str]] | None = None,
    ) -> dict[str, int]:
        """Apply rename inside the DB session.

        Args:
            old_code: Current course code.
            new_code: Proposed replacement course code.
            commit: Whether to commit immediately.
            path_rewrites: Optional `(old_prefix, new_prefix)` pairs to rewrite `artifact_jobs.output_file`.

        Returns:
            Table-name to affected row-count mapping.
        """
        ...

    def commit(self) -> None:
        """Commit the active DB transaction."""
        ...

    def rollback(self) -> None:
        """Roll back the active DB transaction."""
        ...


def _safe_note_state_key(name: str) -> str:
    """Match NoteStateManager filename sanitization for `<key>.json` and `<key>.pause.json`.

    Args:
        name: Course code string.

    Returns:
        Filesystem-safe stem matching `services/notes/state_manager.py`.
    """
    cleaned = re.sub(r"[^\w\-.]+", "_", name.strip()).lstrip(".")
    return cleaned or "default"


def _has_qa_frontmatter_code(path: Path, code: str) -> bool:
    """Check whether a Markdown file's leading YAML frontmatter references `code`.

    Args:
        path: Markdown file path.
        code: Course code to look for.

    Returns:
        True when `course:` or `course_code:` in frontmatter matches `code`.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return False
    key_re = re.compile(
        rf"^(?:course|course_code)\s*:\s*([\"']?){re.escape(code)}\1\s*(?:#.*)?$", re.MULTILINE
    )
    return key_re.search(match.group(2)) is not None


def _restore_file_text(path: Path, text: str, remove_path: Path | None = None) -> Callable[[], None]:
    """Create a typed rollback callback restoring `path` text and optionally deleting `remove_path`.

    Args:
        path: Original file path to restore.
        text: Original UTF-8 file contents.
        remove_path: New destination path to unlink on rollback when distinct from `path`.

    Returns:
        Zero-argument rollback callable.
    """

    def _undo() -> None:
        """Restore original file bytes and remove migrated destination file."""
        path.write_text(text, encoding="utf-8")
        if remove_path is not None and remove_path != path:
            remove_path.unlink(missing_ok=True)

    return _undo


def _restore_moved_dir(src: Path, dst: Path) -> Callable[[], None]:
    """Create a typed rollback callback moving `dst` back to `src`.

    Args:
        src: Original directory path.
        dst: Destination directory path created by move.

    Returns:
        Zero-argument rollback callable.
    """

    def _undo() -> None:
        """Move renamed scratch directory back to original location."""
        if dst.exists():
            shutil.move(str(dst), str(src))

    return _undo


def _rollback_files(undo: list[Callable[[], None]]) -> None:
    """Execute filesystem rollback callbacks in reverse order without masking prior errors.

    Args:
        undo: Stack of rollback callbacks.
    """
    for fn in reversed(undo):
        try:
            fn()
        except Exception:
            logger.exception("Failed reverting file change during course rename rollback")


def _sync_qa_notes_frontmatter(
    qa_files: list[Path], old_code: str, new_code: str, undo: list[Callable[[], None]]
) -> int:
    """Update `course:` / `course_code:` keys inside YAML frontmatter only, recording undo callbacks.

    Args:
        qa_files: Candidate QA Markdown file paths.
        old_code: Previous course code.
        new_code: Replacement course code.
        undo: Stack of rollback callbacks appended in order of modification.

    Returns:
        Number of QA Markdown files updated.
    """
    key_re = re.compile(
        rf"^((?:course|course_code)\s*:\s*)([\"']?){re.escape(old_code)}\2(\s*(?:#.*)?)$", re.MULTILINE
    )
    updated = 0
    for path in qa_files:
        original = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(original)
        if match is None:
            continue
        new_fm = key_re.sub(rf"\g<1>\g<2>{new_code}\g<2>\g<3>", match.group(2))
        if new_fm == match.group(2):
            continue
        new_text = f"{match.group(1)}{new_fm}{match.group(3)}{original[match.end() :]}"
        undo.append(_restore_file_text(path, original))
        path.write_text(new_text, encoding="utf-8")
        updated += 1
    return updated


def _sync_course_toml(
    toml_path: Path | None, old_code: str, new_code: str, undo: list[Callable[[], None]]
) -> int:
    """Update `code = "..."` in `course.toml` and push a restore callback on `undo`.

    Args:
        toml_path: Path to `course.toml` or None when absent.
        old_code: Previous course code.
        new_code: Replacement course code.
        undo: Rollback callback stack.

    Returns:
        `1` if updated, otherwise `0`.
    """
    if toml_path is None or not toml_path.is_file():
        return 0
    original = toml_path.read_text(encoding="utf-8")
    code_re = re.compile(rf'^(code\s*=\s*)(["\']){re.escape(old_code)}\2(\s*(?:#.*)?)$', re.MULTILINE)
    updated = code_re.sub(rf"\g<1>\g<2>{new_code}\g<2>\g<3>", original)
    if updated == original:
        return 0
    undo.append(_restore_file_text(toml_path, original))
    toml_path.write_text(updated, encoding="utf-8")
    return 1


def _sync_notes_state_files(
    state_files: list[tuple[Path, Path]], old_code: str, new_code: str, undo: list[Callable[[], None]]
) -> int:
    """Rename note state JSON / pause JSON files and rewrite `course_key`, recording undo callbacks.

    Args:
        state_files: List of `(src_path, dst_path)` pairs.
        old_code: Previous course code.
        new_code: Replacement course code.
        undo: Rollback callback stack.

    Returns:
        Number of state files migrated.
    """
    for src, dst in state_files:
        if dst != src and dst.exists():
            raise ValueError(f"筆記狀態目標檔案已存在：{dst}")
        raw = src.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if isinstance(payload, dict) and payload.get("course_key") == old_code:
            payload["course_key"] = new_code
        dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if dst != src:
            src.unlink()
        undo.append(_restore_file_text(src, raw, remove_path=dst))
    return len(state_files)


def _move_scratch_dir(scratch_src: Path | None, scratch_dst: Path, undo: list[Callable[[], None]]) -> int:
    """Move `scratch/notes/<old>` to `scratch/notes/<new>` and push reverse move on `undo`.

    Args:
        scratch_src: Existing source scratch directory or None.
        scratch_dst: Destination scratch directory.
        undo: Rollback callback stack.

    Returns:
        `1` if moved, otherwise `0`.
    """
    if scratch_src is None or not scratch_src.is_dir():
        return 0
    if scratch_dst.exists():
        raise ValueError(f"暫存草稿目標資料夾已存在：{scratch_dst}")
    scratch_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(scratch_src), str(scratch_dst))
    undo.append(_restore_moved_dir(scratch_src, scratch_dst))
    return 1


def _sync_all_files(
    targets: dict[str, Any], old_code: str, new_code: str, undo: list[Callable[[], None]]
) -> dict[str, int]:
    """Synchronize all local files for a course-code rename and record undo callbacks.

    Args:
        targets: Collected filesystem target paths from `_collect_file_targets`.
        old_code: Current course code.
        new_code: Replacement course code.
        undo: Stack of rollback callbacks appended as files are modified.

    Returns:
        Dictionary of updated file counts per artifact kind.
    """
    scratch_src, scratch_dst = targets["scratch_src"], targets["scratch_dst"]
    toml_n = _sync_course_toml(targets["toml"], old_code, new_code, undo)
    state_n = _sync_notes_state_files(targets["state_files"], old_code, new_code, undo)
    rewrite_migrated_state_stitched_paths(targets["state_files"], old_code, new_code, scratch_dst.parent)
    scratch_n = _move_scratch_dir(scratch_src, scratch_dst, undo)
    out_n = move_dir_pairs(targets["output_pairs"], undo, "後備輸出")
    rev_n = move_dir_pairs(targets["review_pairs"], undo, "needs_review ")
    qa_files = [
        scratch_dst / p.relative_to(scratch_src) if scratch_src and p.is_relative_to(scratch_src) else p
        for p in targets["qa_files"]
    ]
    qa_n = _sync_qa_notes_frontmatter(qa_files, old_code, new_code, undo)
    return {
        "course_toml": toml_n,
        "notes_state": state_n,
        "scratch_notes": scratch_n,
        "course_output": out_n,
        "needs_review": rev_n,
        "qa_notes": qa_n,
    }


class CourseLifecycleService:
    """Orchestrates course archival, restoration, and atomic course-code renaming."""

    def __init__(
        self,
        course_repo: CourseRepositoryProtocol,
        queue_repo: QueueRepositoryProtocol,
        identity_repo: CourseIdentityRepositoryProtocol,
        config: AppConfig,
    ) -> None:
        """Bind repositories and application config.

        Args:
            course_repo: Course repository.
            queue_repo: Queue repository.
            identity_repo: Transactional course identity repository.
            config: Application configuration.
        """
        self.course_repo = course_repo
        self.queue_repo = queue_repo
        self.identity_repo = identity_repo
        self.config = config

    def _require_course(self, code: str) -> Course:
        """Load a course or raise ValueError if absent.

        Args:
            code: Course code.

        Returns:
            Loaded `Course` domain model.
        """
        course = self.course_repo.get_course(code)
        if course is None:
            raise ValueError(f"找不到課程：{code}")
        return course

    def _set_status(self, code: str, status: CourseStatus) -> dict[str, Any]:
        """Persist a new lifecycle `status` for `code`.

        Args:
            code: Course code.
            status: Target `CourseStatus`.

        Returns:
            Status summary dictionary with `code` and `status`.
        """
        course = self._require_course(code)
        updated = dataclasses.replace(course, status=status)
        self.course_repo.save_course(updated)
        logger.info("Updated course %s status to %s", code, status.value)
        return {"code": code, "status": status.value}

    def archive(self, code: str) -> dict[str, Any]:
        """Archive an active course so it leaves the queue, Today view, and due reviews.

        Args:
            code: Course code.

        Returns:
            Status summary dictionary with `code` and `status`.
        """
        return self._set_status(code, CourseStatus.ARCHIVED)

    def restore(self, code: str) -> dict[str, Any]:
        """Restore an archived course back to active study and queue eligibility.

        Args:
            code: Course code.

        Returns:
            Status summary dictionary with `code` and `status`.
        """
        return self._set_status(code, CourseStatus.ACTIVE)

    def _collect_file_targets(self, course: Course, old_code: str, new_code: str) -> dict[str, Any]:
        """Discover all local files that must stay in sync when renaming `old_code` -> `new_code`.

        Args:
            course: Loaded `Course` object.
            old_code: Current course code.
            new_code: Replacement course code.

        Returns:
            Dictionary describing `toml`, `state_files`, `scratch_src`, `scratch_dst`, `qa_files`, and counts.
        """
        study_root = Path(course.study_dir) if course.study_dir else None
        toml_path = (
            study_root / "course.toml" if study_root and (study_root / "course.toml").is_file() else None
        )
        state_files = collect_state_pairs(self.config.notes_state_dir, old_code, new_code)
        scratch_root = self.config.scratch_kind_dir("notes")
        scratch_src = scratch_root / old_code if (scratch_root / old_code).is_dir() else None
        output_pairs, review_pairs = collect_legacy_and_review_pairs(self.config, course, old_code, new_code)
        qa_files = self._collect_qa_files(study_root, scratch_src, old_code)
        return build_rename_target_bundle(
            {
                "toml": toml_path,
                "state_files": state_files,
                "scratch_src": scratch_src,
                "scratch_dst": scratch_root / new_code,
                "output_pairs": output_pairs,
                "review_pairs": review_pairs,
                "qa_files": qa_files,
            }
        )

    def _collect_qa_files(
        self, study_root: Path | None, scratch_src: Path | None, old_code: str
    ) -> list[Path]:
        """Collect QA Markdown files under study notes folders or scratch notes referencing `old_code`.

        Args:
            study_root: Course study directory if configured.
            scratch_src: Course scratch notes folder if present.
            old_code: Current course code.

        Returns:
            Ordered list of matching Markdown paths.
        """
        candidates: list[Path] = []
        if study_root is not None and study_root.is_dir():
            for notes_dir in self.config.study_layout.category_dirs(study_root, CategoryRole.NOTES):
                qa_dir = notes_dir / "QA_Notes"
                if qa_dir.is_dir():
                    candidates.extend(sorted(qa_dir.glob("*.md")))
        if scratch_src is not None and scratch_src.is_dir():
            candidates.extend(sorted(scratch_src.glob("*.md")))
        return [p for p in candidates if _has_qa_frontmatter_code(p, old_code)]

    def rename(self, old_code: str, new_code: str, *, dry_run: bool = True) -> dict[str, Any]:
        """Preview or transactionally execute a safe course-code rename without moving study folders.

        Args:
            old_code: Current course code.
            new_code: Replacement course code.
            dry_run: When True (default), compute counts without modifying DB or files.

        Returns:
            Result dictionary containing `dry_run`, `old_code`, `new_code`, `tables`, and `files`.
        """
        validate_path_segment(new_code, "course_code")
        table_counts = self.identity_repo.preview_rename(old_code, new_code)
        check_active_locks(self.config, old_code, table_counts.get("literature_items", 0))
        course = self._require_course(old_code)
        targets = self._collect_file_targets(course, old_code, new_code)
        if dry_run:
            return {
                "dry_run": True,
                "old_code": old_code,
                "new_code": new_code,
                "tables": table_counts,
                "files": targets["counts"],
            }
        return self._apply_rename(old_code, new_code, targets)

    def _apply_rename(self, old_code: str, new_code: str, targets: dict[str, Any]) -> dict[str, Any]:
        """Apply DB and local-file updates inside a single rollback-safe unit of work.

        Args:
            old_code: Current course code.
            new_code: Replacement course code.
            targets: Collected filesystem target paths from `_collect_file_targets`.

        Returns:
            Result dictionary with applied counts.
        """
        undo: list[Callable[[], None]] = []
        path_rewrites = build_path_rewrites(targets)
        try:
            table_counts = self.identity_repo.rename_code(
                old_code, new_code, commit=False, path_rewrites=path_rewrites
            )
            file_counts = _sync_all_files(targets, old_code, new_code, undo)
            self.identity_repo.commit()
        except Exception:
            _rollback_files(undo)
            self.identity_repo.rollback()
            raise
        logger.info("Applied course rename %s -> %s", old_code, new_code)
        return {
            "dry_run": False,
            "old_code": old_code,
            "new_code": new_code,
            "tables": table_counts,
            "files": file_counts,
        }

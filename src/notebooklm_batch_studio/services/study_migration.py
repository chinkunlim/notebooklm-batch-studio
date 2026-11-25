"""Idempotent migration of legacy flat course folders into `<term>/<subject>/<category>`."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.study_hierarchy import (
    CourseMigrationTarget,
    ensure_course_study_tree,
    parse_term_subject,
    resolve_course_study_dir,
    resolve_notebooklm_notes_dir,
    resolve_qa_notes_dir,
)
from notebooklm_batch_studio.domain.study_layout import DEFAULT_LAYOUT, CategoryRole

logger = logging.getLogger(__name__)


class MigratableCourseLike(Protocol):
    """Minimal course attributes needed by the migration service."""

    code: str
    name: str
    source_dir: str
    term: str
    subject: str
    study_dir: str


class StudyMigrationRepoProtocol(Protocol):
    """Repository protocol for listing and updating courses during migration."""

    def list_courses(self) -> list[Any]:
        """Return all courses eligible for migration."""
        ...

    def apply_course_migration(self, target: CourseMigrationTarget) -> None:
        """Update database paths for one migrated course.

        Args:
            target: Course code with its resolved term, subject, study folder, and notes folder.
        """
        ...

    def commit(self) -> None:
        """Commit pending database updates."""
        ...


@dataclass(frozen=True)
class CourseMigrationItem:
    """Preview/result of migrating one course into the unified study hierarchy.

    Attributes:
        code: Course code.
        name: Course display name.
        term: Resolved academic term.
        subject: Resolved subject name.
        old_source_dir: Previous input directory.
        new_study_dir: Target `<study_root>/<term>/<subject>` directory.
        moved_pdfs: Number of PDF files moved into `02 Handouts`.
        moved_outputs: Number of output entries moved into `03 Notes/NotebookLM`.
        status: `migrated`, `already_migrated`, or `planned`.
    """

    code: str
    name: str
    term: str
    subject: str
    old_source_dir: str
    new_study_dir: str
    moved_pdfs: int
    moved_outputs: int
    status: str


def _move_children(src: Path, dst: Path, skip_names: set[str], dry_run: bool) -> int:
    """Move non-skipped items from `src` into `dst` without overwriting existing files.

    Args:
        src: Source directory.
        dst: Destination directory.
        skip_names: Filenames to leave untouched (e.g. `course.toml`, hidden files).
        dry_run: When True, only count items without modifying disk.

    Returns:
        Count of moved (or would-be moved) entries.
    """
    if not src.is_dir():
        return 0
    count = 0
    if not dry_run:
        dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.iterdir()):
        if item.name.startswith(".") or item.name in skip_names or (dst / item.name).exists():
            continue
        count += 1
        if not dry_run:
            shutil.move(str(item), str(dst / item.name))
    return count


def _resolve_target(config: AppConfig, course: MigratableCourseLike) -> tuple[str, str, Path]:
    """Determine `(term, subject, study_dir)` for an existing course.

    Args:
        config: Application configuration.
        course: Course DTO.

    Returns:
        Tuple of `(term, subject, new_study_dir)`.
    """
    src_name = Path(course.source_dir).name if course.source_dir else ""
    term, subject = parse_term_subject(src_name or course.name)
    if term == "general" and course.name:
        term, subject = parse_term_subject(course.name)
    term = course.term or term
    subject = course.subject or subject
    return term, subject, resolve_course_study_dir(config.study_root_dir, term, subject, course.code)


def _is_inside_study_root(config: AppConfig, study_dir: str) -> bool:
    """Return True when `study_dir` is an existing folder under `config.study_root_dir`.

    Args:
        config: Application configuration.
        study_dir: Course study directory stored in the database (may be empty).

    Returns:
        Whether the course already lives in the unified study tree.
    """
    if not study_dir:
        return False
    path = Path(study_dir)
    return path.is_dir() and path.resolve().is_relative_to(config.study_root_dir.resolve())


def _move_legacy_outputs(legacy_out: Path, study_dir: Path, dry_run: bool) -> int:
    """Move legacy outputs (`notes/` and generated artifacts) into `03 Notes`.

    Args:
        legacy_out: Legacy `<data_dir>/output/courses/<code>` directory.
        study_dir: Target unified course study directory.
        dry_run: Preview mode flag.

    Returns:
        Count of moved output entries.
    """
    if not legacy_out.is_dir():
        return 0
    moved = 0
    if (legacy_out / "notes").is_dir():
        moved += _move_children(legacy_out / "notes", resolve_qa_notes_dir(study_dir), set(), dry_run=dry_run)
    moved += _move_children(legacy_out, resolve_notebooklm_notes_dir(study_dir), {"notes"}, dry_run=dry_run)
    return moved


def _relocate_course_files(
    src_dir: Path, study_dir: Path, legacy_out: Path, dry_run: bool
) -> tuple[int, int]:
    """Move a course's PDFs into `02 Handouts` and its legacy outputs into `03 Notes`.

    Args:
        src_dir: Previous course input directory.
        study_dir: Target unified course study directory.
        legacy_out: Legacy `<data_dir>/output/courses/<code>` directory.
        dry_run: Preview mode flag.

    Returns:
        Tuple of `(moved_pdfs, moved_outputs)`.
    """
    if not dry_run:
        ensure_course_study_tree(study_dir)
        if (src_dir / "course.toml").is_file() and not (study_dir / "course.toml").is_file():
            shutil.move(str(src_dir / "course.toml"), str(study_dir / "course.toml"))
    skip = {name for role in CategoryRole for name in DEFAULT_LAYOUT.all_names(role)} | {"course.toml"}
    handouts_dir = DEFAULT_LAYOUT.primary_dir(study_dir, CategoryRole.HANDOUTS)
    moved_pdfs = _move_children(src_dir, handouts_dir, skip, dry_run)
    return moved_pdfs, _move_legacy_outputs(legacy_out, study_dir, dry_run=dry_run)


def _remove_if_empty(folder: Path, keep: Path) -> None:
    """Remove a now-empty legacy folder (never `keep`).

    Args:
        folder: Folder that may be empty after migration.
        keep: Folder that must never be removed.
    """
    if folder.is_dir() and folder != keep and not any(folder.iterdir()):
        folder.rmdir()
        logger.info("Removed empty legacy folder %s", folder)


def _migrate_one_course(
    repo: StudyMigrationRepoProtocol,
    config: AppConfig,
    course: MigratableCourseLike,
    dry_run: bool,
) -> CourseMigrationItem:
    """Migrate (or preview) a single course into `<study_root>/<term>/<subject>`.

    Args:
        repo: Migration repository.
        config: Application configuration.
        course: Course DTO.
        dry_run: Preview mode flag.

    Returns:
        `CourseMigrationItem` summary.
    """
    term, subject, study_dir = _resolve_target(config, course)
    src_dir = Path(course.source_dir) if course.source_dir else (config.courses_input_dir / course.code)
    legacy_out = config.courses_output_dir / course.code
    if _is_inside_study_root(config, course.study_dir):
        # Refs: ISSUE-069 — never move a course out of its existing (e.g. school-named) study folder.
        logger.info("Skip migration for %s: already in %s", course.code, course.study_dir)
        existing = (course.code, course.name, term, subject, str(src_dir), course.study_dir)
        return CourseMigrationItem(*existing, 0, 0, "already_migrated")
    summary = (course.code, course.name, term, subject, str(src_dir), str(study_dir))

    if bool(course.study_dir) and Path(course.study_dir) == study_dir and src_dir == study_dir:
        return CourseMigrationItem(*summary, 0, 0, "already_migrated")

    moved_pdfs, moved_outputs = _relocate_course_files(src_dir, study_dir, legacy_out, dry_run)
    if not dry_run:
        notes_dir = resolve_notebooklm_notes_dir(study_dir)
        repo.apply_course_migration(CourseMigrationTarget(course.code, term, subject, study_dir, notes_dir))
        _remove_if_empty(src_dir, keep=study_dir)
        _remove_if_empty(legacy_out, keep=study_dir)
    return CourseMigrationItem(*summary, moved_pdfs, moved_outputs, "planned" if dry_run else "migrated")


def migrate_courses_to_study_hierarchy(
    repo: StudyMigrationRepoProtocol,
    config: AppConfig,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Migrate existing courses from legacy `input/courses` + `output/courses` into `study_root_dir`.

    Args:
        repo: Migration repository implementing `StudyMigrationRepoProtocol`.
        config: Application configuration.
        dry_run: When True, report planned moves without modifying disk or DB.

    Returns:
        Summary dict with `dry_run`, `study_root_dir`, and per-course `items`.
    """
    items = [_migrate_one_course(repo, config, course, dry_run=dry_run) for course in repo.list_courses()]
    if not dry_run:
        repo.commit()
        logger.info("Migrated %d courses to unified study hierarchy at %s", len(items), config.study_root_dir)
    return {
        "dry_run": dry_run,
        "study_root_dir": str(config.study_root_dir),
        "items": [item.__dict__ for item in items],
    }

"""Dry-run-first legacy data consolidation into the unified study tree (Refs: SPEC-014 Task 15, ADR-015)."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.services.course_lifecycle import CourseLifecycleService
from notebooklm_batch_studio.services.legacy_consolidation_ops import (
    ActionType,
    ConsolidationRequest,
    ConsolidationStep,
    apply_folder_rename_step,
    apply_merge_step,
    apply_move_step,
    collect_inventory_rows,
    has_running_note_state,
    unique_dest_path,
)
from notebooklm_batch_studio.services.legacy_consolidation_planner import (
    build_course_dir_index,
    plan_assignments,
    plan_input_moves,
    plan_legacy_notes,
    plan_singular_merges,
)
from notebooklm_batch_studio.services.notes.note_sync import import_legacy_notes

logger = logging.getLogger(__name__)

__all__ = [
    "ActionType",
    "ConsolidationDeps",
    "ConsolidationRepoProtocol",
    "ConsolidationRequest",
    "ConsolidationStep",
    "apply_consolidation",
    "plan_consolidation",
    "save_consolidation_report",
]


class ConsolidationRepoProtocol(Protocol):
    """Repository protocol for listing courses and rewriting path columns transactionally."""

    def list_courses(self) -> list[Course]:
        """Return all registered courses."""
        ...

    def has_running_jobs(self) -> bool:
        """Return True if any queue job is currently running."""
        ...

    def rewrite_course_folder_paths(
        self, old_dir: str, new_dir: str, meta: dict[str, str] | None = None
    ) -> dict[str, int]:
        """Rewrite DB course/job path fields referencing `old_dir` without committing.

        Args:
            old_dir: Old folder path string.
            new_dir: Replacement folder path string.
            meta: Optional `subject`/`course_no` updates.

        Returns:
            Updated row counts per table.
        """
        ...

    def rewrite_category_name(
        self, old_category: str, new_category: str, course_code: str | None = None
    ) -> dict[str, int]:
        """Update DB lecture/literature category names from singular to plural.

        Args:
            old_category: Legacy singular category folder name.
            new_category: Canonical plural category folder name.
            course_code: Optional course filter.

        Returns:
            Updated row counts per table.
        """
        ...

    def update_lecture_relative_path(self, course_code: str, old_rel: str, new_rel: str) -> int:
        """Update exact lecture `relative_path` when a colliding PDF is suffixed.

        Args:
            course_code: Owning course code.
            old_rel: Previous relative path inside course directory.
            new_rel: Actual destination relative path after suffixing.

        Returns:
            Number of updated rows.
        """
        ...

    def commit(self) -> None:
        """Commit pending changes."""
        ...

    def rollback(self) -> None:
        """Roll back pending changes."""
        ...


@dataclass(frozen=True)
class ConsolidationDeps:
    """Injected adapters and exclusive-guard callbacks for `apply_consolidation`."""

    repo: ConsolidationRepoProtocol
    lifecycle: CourseLifecycleService
    check_server_idle: Callable[[], bool] | None = None
    acquire_lock: Callable[[], AbstractContextManager[Any]] | None = None
    is_literature_locked: Callable[[], bool] | None = None


def plan_consolidation(
    config: AppConfig,
    request: ConsolidationRequest,
    repo: ConsolidationRepoProtocol | None = None,
) -> list[ConsolidationStep]:
    """Build a non-destructive row-by-row consolidation plan without modifying disk or DB.

    Args:
        config: Application configuration.
        request: Code, folder, assignment, and NoteStudio mappings.
        repo: Optional DB repository for matching registered courses.

    Returns:
        Ordered list of `ConsolidationStep` entries covering all consolidation operations.
    """
    courses = repo.list_courses() if repo is not None else []
    code_to_dir, old_to_new, folder_pairs = build_course_dir_index(config, request, courses)
    steps: list[ConsolidationStep] = [
        ConsolidationStep("rename_code", old_c, new_c, f"變更課程代碼 {old_c} -> {new_c}")
        for old_c, new_c in request.code_maps.items()
    ]
    for old_str, new_str in folder_pairs:
        note = f"改名為校方命名 {Path(new_str).name} 並同步資料庫與筆記狀態路徑"
        steps.append(ConsolidationStep("rename_folder", old_str, new_str, note))
    steps.extend(plan_singular_merges(config, old_to_new))
    steps.extend(plan_input_moves(config, code_to_dir, request.code_maps))
    assign_steps, assigned_paths = plan_assignments(config, request, code_to_dir)
    steps.extend(assign_steps)
    steps.extend(plan_legacy_notes(config, request, code_to_dir, courses))
    mapped_keys = set(old_to_new.keys()) | set(request.folder_maps.keys())
    inv_rows = collect_inventory_rows(
        config.data_dir, config.study_root_dir, config.deleted_dir, (assigned_paths, mapped_keys)
    )
    steps.extend(ConsolidationStep("inventory", src, tgt, note) for src, tgt, note in inv_rows)
    logger.info("Planned %d consolidation steps", len(steps))
    return steps


def save_consolidation_report(
    config: AppConfig,
    steps: list[ConsolidationStep],
    *,
    applied: bool = False,
    summary: dict[str, int] | None = None,
) -> Path:
    """Persist consolidation plan/results as a traceable JSON report inside `DATA_DIR/diagnostics/`.

    Args:
        config: Application configuration.
        steps: Planned or applied steps.
        applied: True when changes were committed; False for dry-run preview.
        summary: Optional per-action apply summary counts.

    Returns:
        Written JSON report `Path` inside `config.diagnostics_reports_dir`.
    """
    config.diagnostics_reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    mode = "apply" if applied else "dry-run"
    report_path = unique_dest_path(config.diagnostics_reports_dir / f"consolidate-{mode}-{stamp}.json")
    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "mode": mode,
        "step_count": len(steps),
        "summary": summary or {},
        "steps": [asdict(step) for step in steps],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved consolidation report: %s", report_path)
    return report_path


def _assert_exclusive_guards(config: AppConfig, deps: ConsolidationDeps) -> None:
    """Enforce ADR-015 guards before executing mutating `--apply` consolidation steps.

    Args:
        config: Application configuration.
        deps: Injected exclusive-guard dependencies.

    Raises:
        RuntimeError: When web server is active, queue/note/literature jobs are active, or lock held.
    """
    if deps.check_server_idle is not None and not deps.check_server_idle():
        raise RuntimeError("本機網頁伺服器仍在執行，請先停止伺服器再執行 consolidate --apply (ADR-015)")
    if deps.repo.has_running_jobs():
        raise RuntimeError("佇列中尚有執行中任務，無法執行 consolidate --apply")
    if has_running_note_state(config.notes_state_dir):
        raise RuntimeError("尚有筆記生成執行中，無法執行 consolidate --apply")
    if deps.is_literature_locked is not None and deps.is_literature_locked():
        raise RuntimeError("文獻下載／辨識任務鎖定中，無法執行 consolidate --apply")


def _execute_single_step(
    config: AppConfig, deps: ConsolidationDeps, step: ConsolidationStep, counts: dict[str, int]
) -> None:
    """Dispatch one `ConsolidationStep` cleanly and increment summary counters.

    Args:
        config: Application configuration.
        deps: Consolidation dependencies.
        step: Step to execute.
        counts: Mutable summary dictionary incremented in-place.
    """
    if step.action == "rename_code":
        deps.lifecycle.rename(step.source, step.target, dry_run=False)
    elif step.action == "rename_folder":
        apply_folder_rename_step(config.notes_state_dir, deps.repo, step.source, step.target)
    elif step.action == "merge":
        apply_merge_step(deps.repo, step.source, step.target)
    elif step.action == "move":
        apply_move_step(step.source, step.target)
    elif step.action == "import_notes":
        import_legacy_notes(Path(step.source), Path(step.target), overwrite=False)
    elif step.action == "inventory":
        counts["inventory"] += 1
        return
    counts[step.action] = counts.get(step.action, 0) + 1
    counts["applied"] += 1


def apply_consolidation(
    config: AppConfig,
    steps: list[ConsolidationStep],
    *,
    deps: ConsolidationDeps,
) -> dict[str, int]:
    """Execute planned consolidation steps under ADR-015 exclusive locks and watcher pause.

    Args:
        config: Application configuration.
        steps: Consolidation plan produced by `plan_consolidation`.
        deps: Injected repository, lifecycle service, and guard callbacks.

    Returns:
        Summary dictionary with `"applied"` total plus per-action execution counts.
    """
    _assert_exclusive_guards(config, deps)
    lock_ctx = deps.acquire_lock() if deps.acquire_lock is not None else nullcontext()
    pause_path = config.consolidate_pause_path
    counts: dict[str, int] = {"applied": 0, "inventory": 0}
    with lock_ctx:
        pause_path.parent.mkdir(parents=True, exist_ok=True)
        pause_path.write_text(f"pid={os.getpid()}\n", encoding="utf-8")
        try:
            for step in steps:
                _execute_single_step(config, deps, step, counts)
        finally:
            pause_path.unlink(missing_ok=True)
    return counts

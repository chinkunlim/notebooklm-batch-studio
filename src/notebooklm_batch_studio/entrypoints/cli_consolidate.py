"""CLI subcommand (`notebooklm-batch-studio consolidate`) for legacy consolidation (Refs: SPEC-014)."""

from __future__ import annotations

import argparse
import logging

from notebooklm_batch_studio.adapters.db.consolidation_repo import ConsolidationRepository
from notebooklm_batch_studio.adapters.db.course_identity_repo import CourseIdentityRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.locks import RunLock
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.config.study_layout import CategoryRole
from notebooklm_batch_studio.entrypoints.port_check import port_is_free
from notebooklm_batch_studio.services.course_lifecycle import CourseLifecycleService
from notebooklm_batch_studio.services.course_rename_files import is_flock_held
from notebooklm_batch_studio.services.legacy_consolidation import (
    ConsolidationDeps,
    ConsolidationRequest,
    ConsolidationStep,
    apply_consolidation,
    plan_consolidation,
    save_consolidation_report,
)

logger = logging.getLogger(__name__)


def add_consolidate_subparser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the `consolidate` CLI subcommand (dry-run by default).

    Args:
        subparsers: Parent argparse subparsers container.
    """
    p = subparsers.add_parser("consolidate", help="整併舊資料至 study 樹狀結構（預設 dry-run）")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="只預覽計畫表與盤點結果，不動檔案或資料庫（預設）"
    )
    mode.add_argument("--apply", action="store_true", help="實際執行整併計畫（需先停止本機伺服器）")
    p.add_argument("--map", dest="code_maps", action="append", default=[], help="代碼對照 OLD=NEW")
    p.add_argument(
        "--folder", dest="folder_maps", action="append", default=[], help="資料夾改名 OLD=NEW_FOLDER"
    )
    p.add_argument(
        "--assign",
        dest="assignments",
        action="append",
        default=[],
        help="散落路徑指派 PATH=CODE:ROLE[/SUB]",
    )
    p.add_argument(
        "--note-map", dest="note_maps", action="append", default=[], help="NoteStudio 對照 SRC=CODE"
    )
    p.add_argument("--save-plan", action="store_true", help="將計畫表寫入 DATA_DIR/diagnostics/ JSON")


def _parse_kv(items: list[str], flag_name: str) -> dict[str, str]:
    """Parse repeatable `KEY=VALUE` CLI flags cleanly.

    Args:
        items: List of raw `KEY=VALUE` argument strings.
        flag_name: CLI flag label used in error messages.

    Returns:
        Ordered mapping dictionary.

    Raises:
        ValueError: When any item lacks `=` or has an empty key/value.
    """
    mapping: dict[str, str] = {}
    for raw in items:
        if "=" not in raw:
            raise ValueError(f"{flag_name} 格式須為 OLD=NEW：{raw!r}")
        k, v = (part.strip() for part in raw.split("=", 1))
        if not k or not v:
            raise ValueError(f"{flag_name} 不可為空白：{raw!r}")
        mapping[k] = v
    return mapping


def _parse_assignments(items: list[str]) -> list[tuple[str, str, CategoryRole, str]]:
    """Parse `--assign PATH=CODE:ROLE[/SUB]` flags into normalized tuples.

    Args:
        items: List of `--assign` strings.

    Returns:
        List of `(path, course_code, CategoryRole, subfolder)` tuples.

    Raises:
        ValueError: When syntax or `CategoryRole` is invalid.
    """
    parsed: list[tuple[str, str, CategoryRole, str]] = []
    for raw in items:
        if "=" not in raw or ":" not in raw.split("=", 1)[1]:
            raise ValueError(f"--assign 格式須為 PATH=CODE:ROLE[/SUB]：{raw!r}")
        src, dest_spec = (p.strip() for p in raw.split("=", 1))
        code, role_spec = (p.strip() for p in dest_spec.split(":", 1))
        role_raw, sub = (role_spec.split("/", 1) + [""])[:2] if "/" in role_spec else (role_spec, "")
        try:
            role = CategoryRole[role_raw.strip().upper()]
        except KeyError as exc:
            raise ValueError(f"--assign 不支援的分類角色 {role_raw!r}") from exc
        parsed.append((src, code, role, sub.strip()))
    return parsed


def _print_plan_table(steps: list[ConsolidationStep]) -> None:
    """Print planned consolidation steps row by row to stdout.

    Args:
        steps: List of `ConsolidationStep` entries to display.
    """
    print(f"📋 整併計畫表（共 {len(steps)} 筆）")
    print(f"{'action':<14} | {'source':<44} | {'target':<44} | note")
    print("-" * 130)
    for step in steps:
        print(f"{step.action:<14} | {step.source:<44} | {step.target:<44} | {step.note}")


def handle_consolidate_cli(config: AppConfig, args: argparse.Namespace) -> int:
    """Execute `notebooklm-batch-studio consolidate` in dry-run (default) or `--apply` mode.

    Args:
        config: Loaded application configuration.
        args: Parsed CLI arguments.

    Returns:
        CLI exit code (0 on success, 1 on validation/guard failure).
    """
    request = ConsolidationRequest(
        code_maps=_parse_kv(args.code_maps, "--map"),
        folder_maps=_parse_kv(args.folder_maps, "--folder"),
        assignments=_parse_assignments(args.assignments),
        note_course_maps=_parse_kv(args.note_maps, "--note-map"),
    )
    engine = create_db_engine(config.database_url)
    with session_scope(engine) as session:
        repo = ConsolidationRepository(session)
        steps = plan_consolidation(config, request, repo=repo)
        _print_plan_table(steps)
        if not args.apply:
            if args.save_plan:
                report = save_consolidation_report(config, steps, applied=False)
                print(f"📝 Dry-run 計畫已存檔：{report}")
            return 0
        lifecycle = CourseLifecycleService(
            CourseRepository(session), QueueRepository(session), CourseIdentityRepository(session), config
        )
        deps = ConsolidationDeps(
            repo=repo,
            lifecycle=lifecycle,
            check_server_idle=lambda: port_is_free(config.http_host, config.http_port),
            acquire_lock=lambda: RunLock(config.consolidate_lock_path),
            is_literature_locked=lambda: is_flock_held(config.literature_job_lock_path),
        )
        summary = apply_consolidation(config, steps, deps=deps)
        report = save_consolidation_report(config, steps, applied=True, summary=summary)
        print(f"✅ 整併執行完成：{summary}｜稽核報告：{report}")
        return 0

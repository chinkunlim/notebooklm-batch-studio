"""CLI subcommand (`notebooklm-batch-studio literature`) replacing standalone `fetch-literature`."""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from dataclasses import replace

from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.adapters.literature.factory import AdapterLiteratureRuntime
from notebooklm_batch_studio.adapters.literature.tracker_md import STATUS_LABELS
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.literature.tracker import ItemStatus
from notebooklm_batch_studio.services.literature.manager import LiteratureManager, ProcessBatchOptions

logger = logging.getLogger(__name__)


def add_literature_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `literature` CLI subcommand and all its flags.

    Args:
        subparsers: Parent argparse subparsers container.
    """
    p = subparsers.add_parser("literature", help="文獻搜尋、下載、狀態檢視與歸檔管理")
    p.add_argument("--course", default=None, help="關聯課程代碼")
    p.add_argument("--add", action="append", default=[], help="新增 APA、標題或 DOI")
    p.add_argument("--status", action="store_true", help="只列出目前文獻狀態")
    p.add_argument("--identify-only", action="store_true", help="只辨識 APA / DOI，不下載 PDF")
    p.add_argument("--no-browser", action="store_true", help="僅使用開放取用，不開啟 Chrome")
    p.add_argument("--interactive", action="store_true", help="人工處理模式（遇驗證或登入等候）")
    p.add_argument("--retry", default="", help="逗號分隔 key：重試下載")
    p.add_argument("--refresh", default="", help="逗號分隔 key：嘗試將作者稿換成正式版")
    p.add_argument("--delete", default="", help="逗號分隔 key：從清單移除")


def _split_csv(raw: str) -> list[str]:
    """Split a comma-separated key list.

    Args:
        raw: Comma-separated keys.

    Returns:
        Non-empty stripped keys.
    """
    return [k.strip() for k in raw.split(",") if k.strip()]


def _print_status(mgr: LiteratureManager, course: str | None) -> None:
    """Print summary counts and items needing attention.

    Args:
        mgr: Configured LiteratureManager.
        course: Optional course filter.
    """
    items = mgr.lit_repo.list_items(course_code=course)
    counts = Counter(item.status for item in items)
    print(f"文獻共 {len(items)} 筆｜暫存區：{mgr.config.literature_dir}")
    for st in ItemStatus:
        if counts[st]:
            print(f"  {STATUS_LABELS.get(st, st.value)}：{counts[st]}")


def _apply_list_edits(mgr: LiteratureManager, args: argparse.Namespace) -> None:
    """Apply `--delete`, `--add`, and `--retry` edits to the tracked literature list.

    Args:
        mgr: Configured LiteratureManager.
        args: Parsed CLI arguments.
    """
    lit_repo = mgr.lit_repo
    for del_key in _split_csv(args.delete):
        lit_repo.delete_item(del_key)
    for entry in args.add:
        mgr.add_entries(entry, course_code=args.course)
    for retry_key in _split_csv(args.retry):
        existing = lit_repo.get_item(retry_key)
        if existing is not None:
            lit_repo.upsert_item(replace(existing, status=ItemStatus.PENDING, note=""))


def _batch_options(args: argparse.Namespace) -> ProcessBatchOptions:
    """Build the processing options from `--retry`, `--refresh`, and mode flags.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Options for `LiteratureManager.process_items`.
    """
    refresh_keys = frozenset(_split_csv(args.refresh))
    retry_keys = _split_csv(args.retry)
    return ProcessBatchOptions(
        keys=retry_keys or (sorted(refresh_keys) if refresh_keys else None),
        refresh_keys=refresh_keys,
        interactive=args.interactive,
        identify_only=args.identify_only,
        no_browser=args.no_browser,
    )


def handle_literature_cli(config: AppConfig, args: argparse.Namespace) -> int:
    """Execute the `literature` CLI subcommand.

    Args:
        config: Application configuration.
        args: Parsed CLI arguments.

    Returns:
        Exit code integer (0 on success).
    """
    engine = create_db_engine(config.database_url)
    with make_session_factory(engine)() as session:
        mgr = LiteratureManager(
            config, LiteratureRepository(session), CourseRepository(session), AdapterLiteratureRuntime(config)
        )
        mgr.sync_untracked_pdfs()
        _apply_list_edits(mgr, args)
        if args.status:
            _print_status(mgr, args.course)
            return 0
        processed = mgr.process_items(_batch_options(args))
        logger.info("Literature CLI processed %d items", len(processed))
        print(f"已處理 {len(processed)} 筆文獻")
        _print_status(mgr, args.course)
    return 0

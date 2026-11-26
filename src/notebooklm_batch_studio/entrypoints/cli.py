"""Command-line entrypoint for Gemini Notebook 學習工作室.

Wires together database repositories, Gemini Notebook adapter, orchestrator service,
and folder watcher to provide batch execution, queue management, status checks,
and directory monitoring. Only entrypoints may print to standard output.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.notebooklm.chrome_login import build_notebook_login_service
from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.adapters.system_notify import send_notification
from notebooklm_batch_studio.config.logging_setup import setup_logging
from notebooklm_batch_studio.config.settings import AppConfig, load_config
from notebooklm_batch_studio.domain.models import JobStatus, ProfileName
from notebooklm_batch_studio.domain.repositories import QueueRepositoryProtocol
from notebooklm_batch_studio.entrypoints.cli_watch import (  # noqa: F401  (tests use these names)
    _BatchEnv,
    _handle_watch,
    _on_pdf_detected,
    _resolve_registered_study_dir,
)
from notebooklm_batch_studio.services.completion_notice import course_complete_hook
from notebooklm_batch_studio.services.notebook_login import LoginInProgressError
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.worker_pool import WorkerPool

logger = logging.getLogger(__name__)


def _browser_login(config: AppConfig, storage_path: Path) -> int:
    """Open real Chrome so the user signs in to Google personally; the session is saved once verified.

    Uses Chrome started normally on its own profile instead of notebooklm-py's Playwright browser,
    which Google refuses (SPEC-022). The program never sees or stores the password (ADR-002).

    Args:
        config: Application configuration.
        storage_path: Where the queue reads the session (shown to the user).

    Returns:
        0 when signed in, 1 otherwise.
    """
    print(f"🌐 已開啟 Chrome，請在視窗中親自登入 Google（最多等 5 分鐘）。憑證會存到：{storage_path}")
    logger.info("Starting Chrome sign-in for Gemini Notebook")
    try:
        result = build_notebook_login_service(config).login(300)
    except LoginInProgressError as exc:
        print(f"⏳ {exc}")
        return 1
    print(("✅ " if result["status"] == "signed_in" else "❌ ") + result["message"])
    return 0 if result["status"] == "signed_in" else 1


def _handle_login(config: AppConfig, browser: bool = False) -> int:
    """Check Gemini Notebook login credentials, or sign in through the browser with `--browser`.

    Args:
        config: Application configuration.
        browser: Open the browser login flow instead of only checking.

    Returns:
        Exit code (0 on success, 1 on missing auth).
    """
    adapter = NotebookLMAdapter(config)
    if browser:
        code = _browser_login(config, adapter.storage_path)
        if code != 0:
            return code
    if adapter.check_auth():
        print(f"✅ Gemini Notebook 認證檔案存在且有效：{adapter.storage_path}")
        return 0

    print("❌ 尚未找到有效登入憑證！")
    print(f"   預期存放路徑：{adapter.storage_path}")
    print("   請執行 `uv run notebooklm-batch-studio login --browser` 在瀏覽器親自登入。")
    return 1


def _handle_status(config: AppConfig, course_code: str | None = None) -> int:
    """Display registered courses and queue statistics.

    Args:
        config: Application configuration.
        course_code: Optional filter for a specific course code.

    Returns:
        Exit code (0).
    """
    engine = create_db_engine(config.database_url)
    with session_scope(engine) as session:
        course_repo = CourseRepository(session)
        queue_repo = QueueRepository(session)

        courses = course_repo.list_courses()
        counts = queue_repo.count_by_status(course_code=course_code)

    print("==================================================")
    print("📊 Gemini Notebook 學習工作室 — 執行與佇列狀態")
    print("==================================================")
    print(f"已註冊課程數：{len(courses)}")
    for c in courses:
        print(f"  - [{c.code}] {c.name} (講次：{len(c.lectures)} | Notebook：{c.notebook_id or '未連結'})")

    print("\n📦 工作佇列計數：")
    for st in JobStatus:
        val = counts.get(st, 0)
        print(f"  - {st.value:<12}: {val}")

    return 0


def _handle_resume(config: AppConfig) -> int:
    """Manually wake up quota-blocked jobs in the queue.

    Args:
        config: Application configuration.

    Returns:
        Exit code (0).
    """
    engine = create_db_engine(config.database_url)
    with session_scope(engine) as session:
        queue_repo = QueueRepository(session)
        awakened = queue_repo.refresh_quota_wait()

    print(f"✅ 已手動喚醒 {awakened} 個配額等待工作，轉換為 PENDING。")
    return 0


@contextmanager
def _queue_session_provider(engine: Any) -> Iterator[QueueRepositoryProtocol]:
    """Provide an isolated queue repository session for worker tasks.

    Args:
        engine: Database engine.

    Yields:
        QueueRepository bound to an active transaction.
    """
    with session_scope(engine) as session:
        yield QueueRepository(session)


async def _execute_batch_pipeline(
    env: _BatchEnv,
    courses_to_run: list[str],
    workers: int,
    wait_quota: bool = False,
) -> None:
    """Run batch initialization, parallel worker pool execution, and reporting.

    Args:
        env: Bundled engine, Gemini Notebook adapter, and config.
        courses_to_run: List of course codes to execute.
        workers: Concurrency worker count.
        wait_quota: Keep running until quota-blocked jobs have resumed and finished.
    """
    with session_scope(env.engine) as session:
        c_repo, q_repo = CourseRepository(session), QueueRepository(session)
        srv = BatchStudioService(
            c_repo,
            q_repo,
            env.adapter,
            env.config,
            queue_provider=lambda: _queue_session_provider(env.engine),
        )
        for code in courses_to_run:
            print(f"🚀 初始化 Gemini Notebook 筆記本與講義來源: {code}...")
            await srv.setup_notebook_and_sources(code)

    pool = WorkerPool(lambda: _queue_session_provider(env.engine), srv.execute_job, concurrency=workers)
    pool.on_course_complete = course_complete_hook(env.config, send_notification)
    if wait_quota:
        print("⏸ 額度用完時會等待重置，時間到自動繼續，全部完成才結束。")
    await pool.run_until_empty(wait_for_quota=wait_quota)

    with session_scope(env.engine) as session:
        srv = BatchStudioService(CourseRepository(session), QueueRepository(session), env.adapter, env.config)
        for code in courses_to_run:
            md_path, html_path = srv.generate_summary(code)
            print(f"📄 已產出課程總覽: {md_path.name}, {html_path.name}")


def _handle_batch(config: AppConfig, args: argparse.Namespace) -> int:
    """Process one or more course folders end-to-end.

    Args:
        config: Application configuration.
        args: Parsed CLI namespace containing `paths`, `workers`, `profile`, `wait_quota`.

    Returns:
        Exit code (0 on success).
    """
    env = _BatchEnv(create_db_engine(config.database_url), NotebookLMAdapter(config), config)
    with session_scope(env.engine) as session:
        service = BatchStudioService(CourseRepository(session), QueueRepository(session), env.adapter, config)
        registered = service.add_course_folders(args.paths, profile=args.profile)
        courses_to_run = [item["code"] for item in registered]

    print(f"✅ 已排入 {len(courses_to_run)} 門課程至工作佇列。啟動 {args.workers} 個 Worker...")
    asyncio.run(_execute_batch_pipeline(env, courses_to_run, args.workers, args.wait_quota))
    print("🎉 批次處理完畢！")
    return 0


def _dispatch_command(args: argparse.Namespace, config: AppConfig) -> int:
    """Dispatch parsed subcommands to corresponding handlers.

    Args:
        args: Parsed CLI namespace arguments.
        config: Application configuration.

    Returns:
        Exit code integer.
    """
    if args.command == "login":
        return _handle_login(config, args.browser)
    if args.command == "status":
        return _handle_status(config, course_code=args.course)
    if args.command == "resume":
        return _handle_resume(config)
    if args.command == "batch":
        return _handle_batch(config, args)
    if args.command == "watch":
        return _handle_watch(config)
    if args.command == "web":
        return _handle_web(config)
    if args.command == "mcp":
        return _handle_mcp(config)
    if args.command == "init-data":
        created = config.ensure_data_dirs()
        print(f"✅ 已初始化資料目錄（共 {len(created)} 項）：{config.study_root_dir} 與 {config.scratch_dir}")
        return 0
    if args.command == "literature":
        from notebooklm_batch_studio.entrypoints.cli_literature import handle_literature_cli

        return handle_literature_cli(config, args)
    if args.command == "consolidate":
        from notebooklm_batch_studio.entrypoints.cli_consolidate import handle_consolidate_cli

        return handle_consolidate_cli(config, args)
    return 0


def _handle_web(config: AppConfig) -> int:
    """Start local web dashboard and REST API server.

    Args:
        config: Application configuration.

    Returns:
        Exit code integer.
    """
    from notebooklm_batch_studio.entrypoints.api import main as web_main

    web_main()
    return 0


def _handle_mcp(config: AppConfig) -> int:
    """Start MCP stdio server for Agent pairings.

    Args:
        config: Application configuration.

    Returns:
        Exit code integer.
    """
    from notebooklm_batch_studio.entrypoints.mcp_server import main as mcp_main

    mcp_main()
    return 0


def _add_batch_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `batch` subcommand arguments on `subparsers`.

    Args:
        subparsers: Parent argparse subparsers container.
    """
    batch_parser = subparsers.add_parser("batch", help="批次掃描課程並執行生成")
    batch_parser.add_argument("paths", nargs="+", help="課程資料夾路徑")
    batch_parser.add_argument("--workers", type=int, default=2, help="平行 Worker 數量")
    batch_parser.add_argument(
        "--profile",
        choices=[p.value for p in ProfileName],
        default=ProfileName.FULL.value,
        help="產出組合：full / quiz-only / exam-prep",
    )
    batch_parser.add_argument(
        "--wait-quota", action="store_true", help="額度用完時等待重置並自動繼續，全部完成才結束"
    )


def _build_cli_parser() -> argparse.ArgumentParser:
    """Build argument parser with all notebooklm-batch-studio CLI subcommands.

    Returns:
        Configured argparse.ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="notebooklm-batch-studio",
        description="Gemini Notebook 學習工作室 — 批次課程筆記本自動化生成系統",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    login_parser = subparsers.add_parser(
        "login", help="檢查 Gemini Notebook 登入憑證（加 --browser 開瀏覽器登入）"
    )
    login_parser.add_argument("--browser", action="store_true", help="開啟瀏覽器，由你親自登入 Google")
    status_parser = subparsers.add_parser("status", help="檢視課程與工作佇列狀態")
    status_parser.add_argument("--course", default=None, help="過濾特定課程代碼")
    subparsers.add_parser("resume", help="手動喚醒配額等待 (quota_wait) 任務")
    _add_batch_subparser(subparsers)
    subparsers.add_parser("watch", help="啟動資料夾監控守護")
    subparsers.add_parser("web", help="啟動本機網頁管理伺服器 (127.0.0.1:8768)")
    subparsers.add_parser("mcp", help="啟動 MCP stdio 伺服器")
    subparsers.add_parser("init-data", help="建立 DATA_DIR 下的 study/ 與 scratch/<種類>/ 資料夾")
    from notebooklm_batch_studio.entrypoints.cli_consolidate import add_consolidate_subparser
    from notebooklm_batch_studio.entrypoints.cli_literature import add_literature_subparser

    add_literature_subparser(subparsers)
    add_consolidate_subparser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse command line arguments and execute requested studio operation.

    Args:
        argv: Command line arguments; defaults to sys.argv[1:].

    Returns:
        Exit code integer.
    """
    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    config = load_config()
    setup_logging(config.log_level, config.logs_dir if config.log_to_file else None)
    if args.command:
        return _dispatch_command(args, config)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

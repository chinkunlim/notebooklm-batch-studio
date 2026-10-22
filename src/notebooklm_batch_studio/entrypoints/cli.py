"""Command-line entrypoint for NotebookLM Batch Studio.

Wires together database repositories, NotebookLM adapter, orchestrator service,
and folder watcher to provide batch execution, queue management, status checks,
and directory monitoring. Only entrypoints may print to standard output.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.config.logging_setup import setup_logging
from notebooklm_batch_studio.config.settings import AppConfig, load_config
from notebooklm_batch_studio.domain.models import GreetingRequest, JobStatus
from notebooklm_batch_studio.domain.repositories import QueueRepositoryProtocol
from notebooklm_batch_studio.services.greeting import create_greeting
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.watcher import CourseWatcher
from notebooklm_batch_studio.services.worker_pool import WorkerPool

logger = logging.getLogger(__name__)


def _handle_login(config: AppConfig) -> int:
    """Check NotebookLM login credentials status.

    Args:
        config: Application configuration.

    Returns:
        Exit code (0 on success, 1 on missing auth).
    """
    adapter = NotebookLMAdapter(config)
    if adapter.check_auth():
        print(f"✅ NotebookLM 認證檔案存在且有效：{adapter.storage_path}")
        return 0

    print("❌ 尚未找到有效登入憑證！")
    print(f"   預期存放路徑：{adapter.storage_path}")
    print("   請執行 `python3 scripts/spike_notebooklm.py login` 完成瀏覽器手動登入。")
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
    print("📊 NotebookLM Batch Studio — 執行與佇列狀態")
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


async def _execute_batch_pipeline(
    engine: Any,
    adapter: NotebookLMAdapter,
    config: AppConfig,
    courses_to_run: list[str],
    workers: int,
) -> None:
    """Run batch initialization, parallel worker pool execution, and reporting.

    Args:
        engine: Database engine.
        adapter: NotebookLM adapter instance.
        config: Application configuration.
        courses_to_run: List of course codes to execute.
        workers: Concurrency worker count.
    """

    @contextmanager
    def q_provider() -> Iterator[QueueRepositoryProtocol]:
        """Provide an isolated queue repository session for worker tasks.

        Yields:
            QueueRepository bound to an active transaction.
        """
        with session_scope(engine) as s:
            yield QueueRepository(s)

    with session_scope(engine) as session:
        c_repo = CourseRepository(session)
        q_repo = QueueRepository(session)
        srv = BatchStudioService(c_repo, q_repo, adapter, config)
        for code in courses_to_run:
            print(f"🚀 初始化 NotebookLM 筆記本與講義來源: {code}...")
            await srv.setup_notebook_and_sources(code)

    pool = WorkerPool(q_provider, srv.execute_job, concurrency=workers)
    await pool.run_until_empty()

    with session_scope(engine) as session:
        c_repo = CourseRepository(session)
        q_repo = QueueRepository(session)
        srv = BatchStudioService(c_repo, q_repo, adapter, config)
        for code in courses_to_run:
            md_path, html_path = srv.generate_summary(code)
            print(f"📄 已產出課程總覽: {md_path.name}, {html_path.name}")


def _handle_batch(config: AppConfig, paths: list[str], workers: int) -> int:
    """Process one or more course folders end-to-end.

    Args:
        config: Application configuration.
        paths: List of course directory paths.
        workers: Number of parallel worker threads.

    Returns:
        Exit code (0 on success).
    """
    engine = create_db_engine(config.database_url)
    adapter = NotebookLMAdapter(config)

    with session_scope(engine) as session:
        course_repo = CourseRepository(session)
        queue_repo = QueueRepository(session)
        service = BatchStudioService(course_repo, queue_repo, adapter, config)

        courses_to_run: list[str] = []
        for p in paths:
            course = service.register_course_folder(Path(p))
            service.enqueue_course_artifacts(course.code)
            courses_to_run.append(course.code)

    print(f"✅ 已排入 {len(courses_to_run)} 門課程至工作佇列。啟動 {workers} 個 Worker...")
    asyncio.run(_execute_batch_pipeline(engine, adapter, config, courses_to_run, workers))
    print("🎉 批次處理完畢！")
    return 0


def _on_pdf_detected(
    course_dir: Path,
    pdf_path: Path,
    engine: Any,
    adapter: NotebookLMAdapter,
    config: AppConfig,
) -> None:
    """Handle arrival of new lecture PDF file by registering and queuing.

    Args:
        course_dir: Course input directory path.
        pdf_path: Newly stabilized PDF path.
        engine: Database engine.
        adapter: NotebookLM adapter.
        config: Application configuration.
    """
    print(f"\n🔔 偵測到新講義檔案：{pdf_path.name}，開始自動註冊並排程...")
    with session_scope(engine) as session:
        c_repo = CourseRepository(session)
        q_repo = QueueRepository(session)
        srv = BatchStudioService(c_repo, q_repo, adapter, config)
        course = srv.register_course_folder(course_dir)
        added = srv.enqueue_course_artifacts(course.code)
        print(f"✅ 已新增 {added} 個產出任務至佇列。")


def _handle_watch(config: AppConfig) -> int:
    """Start continuous folder monitoring for incoming course lectures.

    Args:
        config: Application configuration.

    Returns:
        Exit code (0 on interrupt).
    """
    watch_root = config.courses_input_dir
    engine = create_db_engine(config.database_url)
    adapter = NotebookLMAdapter(config)

    def callback(c_dir: Path, p_path: Path) -> None:
        """Forward detected lecture PDF to detection handler.

        Args:
            c_dir: Course input directory.
            p_path: New PDF file path.
        """
        _on_pdf_detected(c_dir, p_path, engine, adapter, config)

    watcher = CourseWatcher(watch_root, callback)
    watcher.start()
    print(f"👀 CourseWatcher 守護中... 監看目錄：{watch_root}")
    print("   按下 Ctrl+C 即可停止監看。")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 停止監看。")
        watcher.stop()
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
        return _handle_login(config)
    if args.command == "status":
        return _handle_status(config, course_code=args.course)
    if args.command == "resume":
        return _handle_resume(config)
    if args.command == "batch":
        return _handle_batch(config, args.paths, args.workers)
    if args.command == "watch":
        return _handle_watch(config)
    if args.command == "web":
        return _handle_web(config)
    if args.command == "mcp":
        return _handle_mcp(config)
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


def main(argv: list[str] | None = None) -> int:
    """Parse command line arguments and execute requested studio operation.

    Args:
        argv: Command line arguments; defaults to sys.argv[1:].

    Returns:
        Exit code integer.
    """
    parser = argparse.ArgumentParser(
        prog="notebooklm-batch-studio",
        description="NotebookLM Batch Studio — 批次課程筆記本自動化生成系統",
    )
    parser.add_argument("--name", default=None, help="Greeting test argument")

    subparsers = parser.add_subparsers(dest="command", help="子命令")
    subparsers.add_parser("login", help="檢查 NotebookLM 登入憑證")

    status_parser = subparsers.add_parser("status", help="檢視課程與工作佇列狀態")
    status_parser.add_argument("--course", default=None, help="過濾特定課程代碼")

    subparsers.add_parser("resume", help="手動喚醒配額等待 (quota_wait) 任務")

    batch_parser = subparsers.add_parser("batch", help="批次掃描課程並執行生成")
    batch_parser.add_argument("paths", nargs="+", help="課程資料夾路徑")
    batch_parser.add_argument("--workers", type=int, default=2, help="平行 Worker 數量")

    subparsers.add_parser("watch", help="啟動資料夾監控守護")
    subparsers.add_parser("web", help="啟動本機網頁管理伺服器 (127.0.0.1:8767)")
    subparsers.add_parser("mcp", help="啟動 MCP stdio 伺服器")

    args = parser.parse_args(argv)
    config = load_config()
    setup_logging(config.log_level, config.logs_dir if config.log_to_file else None)

    if args.name is not None and args.command is None:
        result = create_greeting(GreetingRequest(user_name=args.name), config)
        print(result.message)
        return 0

    if args.command:
        return _dispatch_command(args, config)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""`watch` command: monitor study/ for new PDFs and subject folders (SPEC-014, SPEC-027, SPEC-028).

Split out of `cli.py` (file size limit). New `02 Handouts` PDFs are registered and scheduled; new
textbook chapters become lectures without scheduling; whole books only get a split hint; and a
background pass fills in 01–05 for new subject folders.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.db.queue_repository import QueueRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import CourseStatus
from notebooklm_batch_studio.domain.path_safety import is_within
from notebooklm_batch_studio.entrypoints.folder_sync import start_folder_sync
from notebooklm_batch_studio.services.course_parser import (
    keep_lecture_source,
    scan_course_directory,
    uses_textbook_lectures,
)
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.watcher import CourseWatcher, watch_kind

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _BatchEnv:
    """Runtime dependencies bundled for CLI batch execution and directory watching."""

    engine: Any
    adapter: NotebookLMAdapter
    config: AppConfig


def _resolve_registered_study_dir(pdf_path: Path, env: _BatchEnv) -> Path | None:
    """Match a changed PDF inside `study/` to an active registered course directory.

    Args:
        pdf_path: Detected PDF file path.
        env: Shared CLI runtime environment.

    Returns:
        Course `study_dir` Path when matched and non-archived, else None.
    """
    with session_scope(env.engine) as session:
        for course in CourseRepository(session).list_courses(status=CourseStatus.ACTIVE):
            if course.study_dir and is_within(pdf_path, Path(course.study_dir)):
                return Path(course.study_dir)
    return None


def _on_pdf_detected(course_dir: Path, pdf_path: Path, env: _BatchEnv) -> None:
    """Handle a new PDF from `watch` according to where it landed (SPEC-027).

    Whole books at the top of `01 Materials` only get a hint; new chapters in a textbook folder become
    lectures without scheduling; `02 Handouts` PDFs are registered and scheduled as before.

    Args:
        course_dir: Course study directory path.
        pdf_path: Newly stabilized PDF path.
        env: Bundled engine, Gemini Notebook adapter, and config.
    """
    kind = watch_kind(course_dir, pdf_path, env.config.study_layout)
    if kind == "textbook":
        logger.info("Whole textbook detected by watch: %s (not split automatically)", pdf_path.name)
        print(f"\n📚 偵測到課本：{pdf_path.name}。請到網頁「批次排程」按「預覽並切割」（不會自動切割）。")
        return
    if kind == "chapter":
        _add_chapter_lectures(course_dir, pdf_path, env)
        return
    _register_handout(course_dir, pdf_path, env)


def _add_chapter_lectures(course_dir: Path, pdf_path: Path, env: _BatchEnv) -> None:
    """Rescan a textbook course so a new chapter becomes a lecture; nothing is scheduled (SPEC-027).

    Args:
        course_dir: Course study directory path.
        pdf_path: New chapter PDF.
        env: Bundled engine, Gemini Notebook adapter, and config.
    """
    layout = env.config.study_layout
    with session_scope(env.engine) as session:
        repo = CourseRepository(session)
        existing = next((c for c in repo.list_courses() if c.study_dir == str(course_dir.resolve())), None)
        if existing is None:
            return
        scanned = scan_course_directory(
            course_dir, custom_code=existing.code, term=existing.term, layout=layout
        )
        course = keep_lecture_source(scanned, existing, layout)
        repo.save_course(course)
    added = len(course.lectures) - len(existing.lectures)
    logger.info("Chapter %s synced for %s: %d new lectures", pdf_path.name, existing.code, added)
    print(f"\n📖 偵測到新章節：{pdf_path.name}，已加入講次（新增 {added} 講）。")
    print("   到網頁按「開始生成」才會產生產出。")


def _register_handout(course_dir: Path, pdf_path: Path, env: _BatchEnv) -> None:
    """Register a new `02 Handouts` PDF and queue its jobs (skipped for textbook courses, ISSUE-073).

    Args:
        course_dir: Course study directory path.
        pdf_path: Newly stabilized PDF path.
        env: Bundled engine, Gemini Notebook adapter, and config.
    """
    print(f"\n🔔 偵測到新講義檔案：{pdf_path.name}，開始自動註冊並排程...")
    with session_scope(env.engine) as session:
        repo = CourseRepository(session)
        resolved_dir = str(course_dir.resolve())
        existing = next((c for c in repo.list_courses() if c.study_dir == resolved_dir), None)
        if existing and uses_textbook_lectures(existing, env.config.study_layout):  # SPEC-025 R4a
            logger.warning(
                "Skipping handout %s: course %s uses textbook chapters", pdf_path.name, existing.code
            )
            print(f"⏭️  {existing.code} 以課本章節為講次，講義不會變成講次，也不排程。")
            return
        srv = BatchStudioService(repo, QueueRepository(session), env.adapter, env.config)
        course = scan_course_directory(
            course_dir,
            custom_code=existing.code if existing else None,
            term=existing.term if existing else "",
            layout=env.config.study_layout,
        )
        repo.save_course(course)
        added = srv.enqueue_course_artifacts(course.code)
        print(f"✅ 已新增 {added} 個產出任務至佇列。")


def _handle_watch(config: AppConfig) -> int:
    """Start continuous folder monitoring for incoming course lectures.

    Watches `config.study_root_dir` and filters to active courses' HANDOUTS PDFs.

    Args:
        config: Application configuration.

    Returns:
        Exit code (0 on interrupt).
    """
    watch_root = config.study_root_dir
    env = _BatchEnv(create_db_engine(config.database_url), NotebookLMAdapter(config), config)
    watcher = CourseWatcher(
        watch_root,
        lambda c_dir, p_path: _on_pdf_detected(c_dir, p_path, env),
        resolve_course=lambda p_path: _resolve_registered_study_dir(p_path, env),
        layout=config.study_layout,
    )
    watcher.set_pause_check(lambda: config.consolidate_pause_path.exists())
    watcher.start()
    folder_sync = start_folder_sync(config, lambda: session_scope(env.engine))  # SPEC-028
    print(f"👀 CourseWatcher 守護中... 監看目錄：{watch_root}")
    print("   按下 Ctrl+C 即可停止監看。")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 停止監看。")
        watcher.stop()
        folder_sync.stop()
    return 0

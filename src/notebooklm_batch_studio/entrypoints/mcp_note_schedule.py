"""MCP tools for the background Gemini note schedule (SPEC-020)."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.entrypoints.mcp_confirm import confirm_warning
from notebooklm_batch_studio.entrypoints.note_runtime import build_note_scheduler
from notebooklm_batch_studio.services.notes.note_scheduler import NoteScheduler

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)


def _dumps(payload: Any) -> str:
    """Serialize a payload as JSON text.

    Args:
        payload: JSON-serializable value.

    Returns:
        JSON string.
    """
    return json.dumps(payload, ensure_ascii=False)


def _register_read_and_add(mcp: MCPServer, scheduler: NoteScheduler, session_factory: Any) -> None:
    """Register `notes_schedule_status` and `notes_schedule_add`.

    Args:
        mcp: MCPServer instance.
        scheduler: Note scheduler (the web server runs the worker thread).
        session_factory: SQLAlchemy session factory.
    """

    @mcp.tool()
    def notes_schedule_status() -> str:
        """Show scheduled Gemini chapters, pause state, and the next quota resume time.

        Returns:
            JSON schedule status.
        """
        return _dumps(scheduler.status())

    @mcp.tool()
    def notes_schedule_add(course_key: str, lecture_nos: list[int], confirm: bool = False) -> str:
        """Approve chapters for background Gemini note generation (runs while the web server is up).

        Args:
            course_key: Course code.
            lecture_nos: Lecture numbers to generate.
            confirm: Must be True to proceed.

        Returns:
            JSON `{added, skipped}` or a confirmation warning.
        """
        if not confirm:
            return confirm_warning("Pass confirm=True to schedule note generation.", course_key=course_key)
        with session_factory() as db:
            course = CourseRepository(db).get_course(course_key)
        if course is None:
            return _dumps({"confirmed": True, "error": f"找不到課程：{course_key}"})
        return _dumps({"confirmed": True, **scheduler.enqueue_course(course, lecture_nos)})


def _register_pause_resume(mcp: MCPServer, scheduler: NoteScheduler) -> None:
    """Register `notes_schedule_pause` and `notes_schedule_resume`.

    Args:
        mcp: MCPServer instance.
        scheduler: Note scheduler.
    """

    @mcp.tool()
    def notes_schedule_pause(confirm: bool = False) -> str:
        """Pause the note schedule after the current module.

        Args:
            confirm: Must be True to proceed.

        Returns:
            JSON status or confirmation warning.
        """
        if not confirm:
            return confirm_warning("Pass confirm=True to pause the note schedule.")
        return _dumps({"confirmed": True, **scheduler.pause()})

    @mcp.tool()
    def notes_schedule_resume(confirm: bool = False) -> str:
        """Resume the note schedule.

        Args:
            confirm: Must be True to proceed.

        Returns:
            JSON status or confirmation warning.
        """
        if not confirm:
            return confirm_warning("Pass confirm=True to resume the note schedule.")
        return _dumps({"confirmed": True, **scheduler.resume()})


def register_note_schedule_tools(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register the note schedule MCP tools.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """
    scheduler = build_note_scheduler(cfg, session_factory)
    _register_read_and_add(mcp, scheduler, session_factory)
    _register_pause_resume(mcp, scheduler)
    logger.debug("Registered note schedule MCP tools")

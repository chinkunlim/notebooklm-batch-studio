"""MCP tools for textbook splitting and moving chapters out of `02 Handouts` (SPEC-018)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.pdf_textbook import PypdfTextbookTools
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import CourseStatus
from notebooklm_batch_studio.entrypoints.mcp_confirm import confirm_warning
from notebooklm_batch_studio.services.textbook_split import TextbookService

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)

Runner = Callable[[Callable[[TextbookService], Any]], str]


def _make_runner(cfg: AppConfig, session_factory: Any) -> Runner:
    """Build a helper that runs a TextbookService call and serializes the result or error.

    Args:
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.

    Returns:
        Callable taking `fn(service)` and returning a JSON string.
    """

    def run(fn: Callable[[TextbookService], Any]) -> str:
        """Run `fn` on a fresh service.

        Args:
            fn: Callable receiving the service.

        Returns:
            JSON string.
        """
        try:
            with session_factory() as db:
                result = fn(TextbookService(cfg, CourseRepository(db), PypdfTextbookTools()))
        except ValueError as exc:  # includes CourseNotFoundError and path-safety errors
            return json.dumps({"confirmed": True, "error": str(exc)}, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)

    return run


def _register_list_tool(mcp: MCPServer, run: Runner) -> None:
    """Register `list_textbooks`.

    Args:
        mcp: MCPServer instance.
        run: Service runner.
    """

    @mcp.tool()
    def list_textbooks(code: str) -> str:
        """List top-level textbook PDFs in a course's 01 Materials folders.

        Args:
            code: Course identifier.

        Returns:
            JSON string with `textbooks`.
        """
        return run(lambda svc: {"textbooks": svc.list_textbooks(code)})


def _register_pending_tool(mcp: MCPServer, run: Runner) -> None:
    """Register `list_pending_textbooks` (Refs: SPEC-020).

    Args:
        mcp: MCPServer instance.
        run: Service runner.
    """

    @mcp.tool()
    def list_pending_textbooks() -> str:
        """List unsplit textbooks in active courses' 01 Materials folders with chapter counts.

        Returns:
            JSON string with `pending`.
        """

        def scan(svc: TextbookService) -> dict[str, Any]:
            """Collect pending textbooks for active courses.

            Args:
                svc: Textbook service.

            Returns:
                `{"pending": [...]}`.
            """
            codes = [c.code for c in svc.course_repo.list_courses(status=CourseStatus.ACTIVE)]  # type: ignore[attr-defined]
            return {"pending": svc.pending_textbooks(codes)}

        return run(scan)


def _register_split_tool(mcp: MCPServer, run: Runner) -> None:
    """Register `split_textbook`.

    Args:
        mcp: MCPServer instance.
        run: Service runner.
    """

    @mcp.tool()
    def split_textbook(code: str, relative_path: str, dry_run: bool = True, confirm: bool = False) -> str:
        """Preview or split a textbook into `01 Materials/<book>/ChNN-Title.pdf` (existing chapters kept).

        Args:
            code: Course identifier.
            relative_path: Path from `list_textbooks`.
            dry_run: Preview only when True.
            confirm: Must be True to proceed.

        Returns:
            JSON chapter plan, result, or confirmation warning.
        """
        if not confirm:
            return confirm_warning("Pass confirm=True to split the textbook.", code=code, dry_run=dry_run)
        return run(lambda svc: {"confirmed": True, **svc.split_textbook(code, relative_path, dry_run)})


def _register_relocate_tool(mcp: MCPServer, run: Runner) -> None:
    """Register `relocate_handouts_to_textbook`.

    Args:
        mcp: MCPServer instance.
        run: Service runner.
    """

    @mcp.tool()
    def relocate_handouts_to_textbook(
        code: str, book_folder: str, dry_run: bool = True, confirm: bool = False
    ) -> str:
        """Preview or move chapter PDFs from 02 Handouts into 01 Materials/<book_folder>/ (numbers kept).

        Args:
            code: Course identifier.
            book_folder: Textbook folder name.
            dry_run: Preview only when True.
            confirm: Must be True to proceed.

        Returns:
            JSON move plan, result, or confirmation warning.
        """
        if not confirm:
            return confirm_warning("Pass confirm=True to move the chapter PDFs.", code=code, dry_run=dry_run)
        return run(lambda svc: {"confirmed": True, **svc.relocate_handouts(code, book_folder, dry_run)})


def register_textbook_tools(mcp: MCPServer, cfg: AppConfig, session_factory: Any) -> None:
    """Register `list_textbooks`, `split_textbook` and `relocate_handouts_to_textbook`.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
    """
    run = _make_runner(cfg, session_factory)
    _register_list_tool(mcp, run)
    _register_pending_tool(mcp, run)
    _register_split_tool(mcp, run)
    _register_relocate_tool(mcp, run)
    logger.debug("Registered textbook MCP tools")

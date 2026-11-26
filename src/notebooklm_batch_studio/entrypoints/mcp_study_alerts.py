"""MCP tool listing missing or changed lecture PDFs (SPEC-029, read-only)."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.services.lecture_files import LectureFileChecker

logger = logging.getLogger(__name__)


def register_lecture_file_tool(mcp: MCPServer, session_factory: Any) -> None:
    """Register `list_lecture_file_issues`.

    Args:
        mcp: MCPServer instance.
        session_factory: SQLAlchemy session factory.
    """
    checker = LectureFileChecker()

    @mcp.tool()
    def list_lecture_file_issues() -> str:
        """List lecture PDFs that are missing (deleted/renamed) or changed (Gemini Notebook has the old one).

        Returns:
            JSON string with `issues` (course_code, course_name, lecture_no, filename, relative_path,
            issue, sha256).
        """
        with session_factory() as db:
            issues = checker.issues(CourseRepository(db).list_courses())
        return json.dumps({"issues": issues}, ensure_ascii=False, indent=2)

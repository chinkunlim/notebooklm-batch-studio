"""MCP tools for the learning aids: lecture key points, memory strength and the tutor."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.services.learning_service import LearningService


def _dump(data: Any) -> str:
    """Serialize a result for an MCP reply.

    Args:
        data: JSON-compatible data.

    Returns:
        Pretty JSON string.
    """
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


async def _generate_key_points_payload(
    learning: LearningService, code: str, lecture_no: int, flags: tuple[bool, bool]
) -> str:
    """Validate confirmation and ask Gemini Notebook for lecture key points.

    Args:
        learning: Learning service.
        code: Course code.
        lecture_no: Lecture number.
        flags: Tuple of `(force, confirm)`.

    Returns:
        JSON string response.
    """
    force, confirm = flags
    if not confirm:
        return _dump({"confirmed": False, "message": "Pass confirm=True to ask Gemini Notebook."})
    try:
        return _dump(await learning.generate_key_points(code, lecture_no, force))
    except Exception as exc:
        return _dump({"error": str(exc)})


async def _ask_tutor_payload(
    learning: LearningService, code: str, message: str, opts: tuple[int | None, bool]
) -> str:
    """Validate confirmation and send a message to the Socratic tutor.

    Args:
        learning: Learning service.
        code: Course code.
        message: Student question text.
        opts: Tuple of `(lecture_no, confirm)`.

    Returns:
        JSON string response.
    """
    lecture_no, confirm = opts
    if not confirm:
        return _dump({"confirmed": False, "message": "Pass confirm=True to ask the tutor."})
    try:
        return _dump(await learning.ask_tutor(code, lecture_no, message))
    except Exception as exc:
        return _dump({"error": str(exc)})


def _register_key_point_tools(mcp: MCPServer, learning: LearningService) -> None:
    """Register lecture key-points read and generation MCP tools.

    Args:
        mcp: MCPServer instance.
        learning: Learning service.
    """

    @mcp.tool()
    def get_key_points(code: str, lecture_no: int) -> str:
        """Saved key points of a lecture: verbatim quote, page, importance, note (read-only).

        Args:
            code: Course code.
            lecture_no: Lecture number.

        Returns:
            JSON string.
        """
        try:
            return _dump(learning.key_points(code, lecture_no))
        except Exception as exc:
            return _dump({"error": str(exc)})

    @mcp.tool()
    async def generate_key_points(
        code: str, lecture_no: int, force: bool = False, confirm: bool = False
    ) -> str:
        """Ask Gemini Notebook for a lecture's key points (requires confirm=True; uses chat quota once).

        Args:
            code: Course code.
            lecture_no: Lecture number.
            force: Ask again even when key points are saved.
            confirm: Must be True to call Gemini Notebook.

        Returns:
            JSON string with the key points or an error.
        """
        return await _generate_key_points_payload(learning, code, lecture_no, (force, confirm))


def _register_memory_and_tutor_tools(mcp: MCPServer, learning: LearningService) -> None:
    """Register memory strength and Socratic tutor MCP tools.

    Args:
        mcp: MCPServer instance.
        learning: Learning service.
    """

    @mcp.tool()
    def get_memory_strength(code: str) -> str:
        """Forgetting-curve memory strength per lecture, study streak and heatmap (read-only).

        Args:
            code: Course code.

        Returns:
            JSON string.
        """
        try:
            return _dump(learning.memory(code))
        except Exception as exc:
            return _dump({"error": str(exc)})

    @mcp.tool()
    async def ask_tutor(code: str, message: str, lecture_no: int | None = None, confirm: bool = False) -> str:
        """Ask the Socratic tutor (requires confirm=True; calls Gemini Notebook and saves the chat).

        Args:
            code: Course code.
            message: The student's message.
            lecture_no: Lecture number, or None for the whole course.
            confirm: Must be True to call Gemini Notebook.

        Returns:
            JSON string with the reply or an error.
        """
        return await _ask_tutor_payload(learning, code, message, (lecture_no, confirm))


def register_learning_tools(mcp: MCPServer, learning: LearningService) -> None:
    """Register learning tools (Gemini Notebook calls and deletions require confirm=True).

    Args:
        mcp: MCPServer instance.
        learning: Learning service.
    """
    _register_key_point_tools(mcp, learning)
    _register_memory_and_tutor_tools(mcp, learning)

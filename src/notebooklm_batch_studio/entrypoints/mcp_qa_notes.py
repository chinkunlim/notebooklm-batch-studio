"""MCP tools for exploratory NotebookLM Q&A, note saving, and source pushing (SPEC-011)."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from notebooklm_batch_studio.entrypoints.mcp_remote_admin import register_remote_extra_tools
from notebooklm_batch_studio.services.qa_notes_service import QANotesService

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)


def _register_qa_read_tools(mcp: MCPServer, qa_notes: QANotesService) -> None:
    """Register read/ask MCP tools (`ask_notebook_question` and `list_course_notes`).

    Args:
        mcp: FastMCP server instance.
        qa_notes: Configured QANotesService.
    """

    @mcp.tool()
    async def ask_notebook_question(code: str, question: str, lecture_no: int | None = None) -> str:
        """Ask a question grounded in a course's Gemini Notebook (all or one lecture).

        Args:
            code: Course code.
            question: Question text.
            lecture_no: Optional lecture sequence number.

        Returns:
            JSON string with `answer`, `conversation_id`, and `references`.
        """
        try:
            res = await qa_notes.ask(code, question, lecture_no=lecture_no)
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def list_course_notes(code: str, tag: str | None = None) -> str:
        """List saved Q&A Markdown notes for a course, optionally filtered by tag.

        Args:
            code: Course code or `*` for all courses.
            tag: Optional tag filter (e.g. `L03`, `進化論`).

        Returns:
            JSON string containing `notes` list.
        """
        return json.dumps({"notes": qa_notes.list_notes(code, tag=tag)}, ensure_ascii=False, indent=2)


def _register_save_note_tool(mcp: MCPServer, qa_notes: QANotesService) -> None:
    """Register the `save_qa_note` MCP tool.

    Args:
        mcp: FastMCP server instance.
        qa_notes: Configured QANotesService.
    """

    @mcp.tool()
    def save_qa_note(
        code: str,
        title: str,
        content_markdown: str,
        lecture_no: int | None = None,
    ) -> str:
        """Save a Q&A answer as a structured Markdown note with hierarchical tags.

        Args:
            code: Course code.
            title: Note heading title.
            content_markdown: Markdown body text.
            lecture_no: Optional lecture sequence number.

        Returns:
            JSON string of the saved note.
        """
        try:
            res = qa_notes.save_note(code, title, content_markdown, lecture_no=lecture_no)
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_push_note_tool(mcp: MCPServer, qa_notes: QANotesService) -> None:
    """Register the `push_note_to_source` MCP tool.

    Args:
        mcp: FastMCP server instance.
        qa_notes: Configured QANotesService.
    """

    @mcp.tool()
    async def push_note_to_source(code: str, note_id: str, confirm: bool = False) -> str:
        """Upload a saved Q&A note as a source PDF to Gemini Notebook (requires confirm=True).

        Args:
            code: Course code.
            note_id: Note identifier.
            confirm: Must be True to upload to Gemini Notebook.

        Returns:
            JSON string confirming upload or confirmation warning.
        """
        if not confirm:
            return json.dumps(
                {"confirmed": False, "warning": "Set confirm=True to upload note to Gemini Notebook."},
                ensure_ascii=False,
            )
        try:
            res = await qa_notes.push_note_to_source(code, note_id)
            res["confirmed"] = True
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def register_qa_notes_tools(mcp: MCPServer, qa_notes: QANotesService) -> None:
    """Register all Q&A notes MCP tools on the FastMCP server.

    Args:
        mcp: FastMCP server instance.
        qa_notes: Configured QANotesService.
    """
    _register_qa_read_tools(mcp, qa_notes)
    _register_save_note_tool(mcp, qa_notes)
    _register_push_note_tool(mcp, qa_notes)


def register_remote_artifact_tools(mcp: MCPServer, service: Any) -> None:
    """Register remote Gemini Notebook artifact listing, deletion, and admin MCP tools.

    Args:
        mcp: FastMCP server instance.
        service: BatchStudioService instance.
    """
    _register_remote_list_delete(mcp, service)
    register_remote_extra_tools(mcp, service)


def _register_remote_list_delete(mcp: MCPServer, service: Any) -> None:
    """Register list_remote_artifacts and delete_remote_artifact MCP tools.

    Args:
        mcp: FastMCP server instance.
        service: BatchStudioService instance.
    """

    @mcp.tool()
    async def list_remote_artifacts(course_code: str) -> str:
        """List remote Gemini Notebook artifacts and mark active local versions.

        Args:
            course_code: Course identifier (e.g. 'BIO101').

        Returns:
            JSON string listing remote artifacts with `in_use` and `is_latest_active` flags.
        """
        return json.dumps(await service.list_remote_artifacts(course_code), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def delete_remote_artifact(
        course_code: str, artifact_id: str, delete_local: bool = False, confirm: bool = False
    ) -> str:
        """Delete a remote Gemini Notebook artifact (requires confirm=True).

        Args:
            course_code: Course identifier (e.g. 'BIO101').
            artifact_id: Remote artifact identifier.
            delete_local: Whether to also delete the local downloaded file.
            confirm: Must be set to True to execute deletion.

        Returns:
            JSON string with deletion summary or confirmation prompt.
        """
        if not confirm:
            return json.dumps({"requires_confirmation": True, "artifact_id": artifact_id}, ensure_ascii=False)
        res = await service.delete_remote_artifact(course_code, artifact_id, delete_local=delete_local)
        return json.dumps(res, ensure_ascii=False, indent=2)

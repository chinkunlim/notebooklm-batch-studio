"""MCP tools for exploratory NotebookLM Q&A, note saving, and source pushing (SPEC-011)."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from notebooklm_batch_studio.entrypoints.mcp_confirm import confirm_warning
from notebooklm_batch_studio.entrypoints.mcp_remote_admin import register_remote_extra_tools
from notebooklm_batch_studio.services.qa_notes_service import AskOptions, QANotesService

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)


class QANoteInput(BaseModel):
    """Content of a Q&A note to save.

    Attributes:
        title: Note heading title.
        content_markdown: Markdown body text.
        lecture_no: Optional lecture sequence number.
    """

    title: str
    content_markdown: str
    lecture_no: int | None = None


def _register_qa_ask_tool(mcp: MCPServer, qa_notes: QANotesService) -> None:
    """Register the `ask_notebook_question` MCP tool.

    Args:
        mcp: FastMCP server instance.
        qa_notes: Configured QANotesService.
    """

    @mcp.tool()
    async def ask_notebook_question(
        code: str, question: str, lecture_no: int | None = None, use_web_search: bool = False
    ) -> str:
        """Ask a question grounded in a course's Gemini Notebook (all or one lecture).

        Args:
            code: Course code.
            question: Question text.
            lecture_no: Optional lecture sequence number.
            use_web_search: Whether to also run web search for supplemental references.

        Returns:
            JSON string with `answer`, `conversation_id`, `references`, and `web_references`.
        """
        try:
            res = await qa_notes.ask(
                code, question, AskOptions(lecture_no=lecture_no, use_web_search=use_web_search)
            )
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_qa_read_tools(mcp: MCPServer, qa_notes: QANotesService) -> None:
    """Register read/ask MCP tools (`ask_notebook_question` and `list_course_notes`).

    Args:
        mcp: FastMCP server instance.
        qa_notes: Configured QANotesService.
    """
    _register_qa_ask_tool(mcp, qa_notes)

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
    def save_qa_note(code: str, note: QANoteInput, confirm: bool = False) -> str:
        """Save a Q&A answer as a structured Markdown note with hierarchical tags (requires confirm=True).

        Args:
            code: Course code.
            note: Note title, Markdown body, and optional lecture number.
            confirm: Must be True to write the note.

        Returns:
            JSON string of the saved note, or a confirmation warning.
        """
        if not confirm:
            return json.dumps(
                {"confirmed": False, "warning": "Confirmation required: pass confirm=True to save the note."},
                ensure_ascii=False,
            )
        try:
            res = qa_notes.save_note(code, note.title, note.content_markdown, lecture_no=note.lecture_no)
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
    _register_reverse_import_tools(mcp, service)
    register_remote_extra_tools(mcp, service)


def _reverse_import_service(service: Any) -> Any:
    """Build ReverseImportService from BatchStudioService.

    Args:
        service: BatchStudioService instance.

    Returns:
        Configured ReverseImportService instance.
    """
    from notebooklm_batch_studio.services.reverse_import import ReverseImportService

    return ReverseImportService(
        notebooklm_client=service.notebooklm_client,
        course_repo=service.course_repo,
        queue_repo=service.queue_repo,
        output_base_dir=service.config.output_dir,
    )


def _register_reverse_import_tools(mcp: MCPServer, service: Any) -> None:
    """Register list_remote_notebooks, import_remote_notebook, and download_course_files_locally MCP tools.

    Args:
        mcp: FastMCP server instance.
        service: BatchStudioService instance.
    """
    _register_list_notebooks_tool(mcp, service)
    _register_import_notebook_tool(mcp, service)
    _register_download_course_files_tool(mcp, service)


def _register_list_notebooks_tool(mcp: MCPServer, service: Any) -> None:
    """Register the read-only list_remote_notebooks MCP tool.

    Args:
        mcp: FastMCP server instance.
        service: BatchStudioService instance.
    """

    @mcp.tool()
    async def list_remote_notebooks() -> str:
        """List all remote Gemini Notebooks and show which ones are linked locally.

        Returns:
            JSON string listing remote notebooks and their linked course codes.
        """
        svc = _reverse_import_service(service)
        return json.dumps(await svc.list_remote_notebooks(), ensure_ascii=False, indent=2)


async def _import_remote_notebook_payload(
    service: Any, notebook_id: str, course_code: str, download_sources: bool
) -> str:
    """Execute confirmed import_remote_notebook workflow.

    Args:
        service: BatchStudioService instance.
        notebook_id: Remote Gemini Notebook identifier.
        course_code: Optional local course code.
        download_sources: Whether to download remote source fulltext.

    Returns:
        JSON string with import result.
    """
    from notebooklm_batch_studio.services.reverse_import import ReverseImportOptions

    svc = _reverse_import_service(service)
    opts = ReverseImportOptions(
        notebook_id=notebook_id,
        course_code=course_code.strip() or None,
        download_sources=download_sources,
        download_artifacts=True,
    )
    return json.dumps(await svc.import_remote_notebook(opts), ensure_ascii=False, indent=2)


def _register_import_notebook_tool(mcp: MCPServer, service: Any) -> None:
    """Register the import_remote_notebook MCP tool with confirm guard.

    Args:
        mcp: FastMCP server instance.
        service: BatchStudioService instance.
    """

    @mcp.tool()
    async def import_remote_notebook(
        notebook_id: str,
        course_code: str = "",
        download_sources: bool = True,
        confirm: bool = False,
    ) -> str:
        """Reverse-import an existing Gemini Notebook as a local course (requires confirm=True).

        Args:
            notebook_id: Remote Gemini Notebook identifier.
            course_code: Optional local course code (auto-derived if empty).
            download_sources: Whether to download remote source fulltext as Markdown.
            confirm: Must be set to True to create the local course and download files.

        Returns:
            JSON string with imported course summary or confirmation prompt.
        """
        if not confirm:
            return confirm_warning(
                "Confirmation required: pass confirm=True to import remote notebook.", notebook_id=notebook_id
            )
        return await _import_remote_notebook_payload(service, notebook_id, course_code, download_sources)


def _register_download_course_files_tool(mcp: MCPServer, service: Any) -> None:
    """Register the download_course_files_locally MCP tool with confirm guard.

    Args:
        mcp: FastMCP server instance.
        service: BatchStudioService instance.
    """

    @mcp.tool()
    async def download_course_files_locally(
        course_code: str,
        include_sources: bool = True,
        include_artifacts: bool = True,
        confirm: bool = False,
    ) -> str:
        """Download all remote sources and artifacts of a linked course to DATA_DIR (requires confirm=True).

        Args:
            course_code: Existing local course code.
            include_sources: Whether to download remote source fulltext as Markdown.
            include_artifacts: Whether to download remote generated artifacts.
            confirm: Must be set to True to download files locally.

        Returns:
            JSON string with downloaded counts and local folder paths.
        """
        if not confirm:
            return confirm_warning(
                "Confirmation required: pass confirm=True to download course files locally.",
                course_code=course_code,
            )
        svc = _reverse_import_service(service)
        res = await svc.download_course_files_locally(
            course_code, include_sources=include_sources, include_artifacts=include_artifacts
        )
        return json.dumps(res, ensure_ascii=False, indent=2)


async def _delete_remote_artifact_payload(
    service: Any, course_code: str, artifact_id: str, delete_local: bool
) -> str:
    """Execute confirmed delete_remote_artifact workflow.

    Args:
        service: BatchStudioService instance.
        course_code: Course identifier.
        artifact_id: Remote artifact identifier.
        delete_local: Whether to also delete local files.

    Returns:
        JSON string with deletion summary.
    """
    res = await service.delete_remote_artifact(course_code, artifact_id, delete_local=delete_local)
    return json.dumps(res, ensure_ascii=False, indent=2)


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
            return confirm_warning(
                "Confirmation required: pass confirm=True to delete remote artifact.", artifact_id=artifact_id
            )
        return await _delete_remote_artifact_payload(service, course_code, artifact_id, delete_local)

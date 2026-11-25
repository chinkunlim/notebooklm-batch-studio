"""MCP tools for Phase 1 modular Markdown note generation (Refs: ADR-012)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from notebooklm_batch_studio.domain.note_pipeline import NoteBackend
from notebooklm_batch_studio.domain.path_safety import PathSafetyError
from notebooklm_batch_studio.services.notes.module_prompts import StepPromptContext
from notebooklm_batch_studio.services.notes.note_files import list_note_files, read_note_file
from notebooklm_batch_studio.services.notes.note_pipeline_service import (
    ChapterNoteRequest,
    NotePipelineService,
)

logger = logging.getLogger(__name__)


class McpNoteGenerateInput(BaseModel):
    """Structured input for `notes_generate_chapter` MCP tool.

    Attributes:
        course_key: Course identifier or folder code.
        course_name: Human-readable course name.
        chapter_id: Chapter identifier (e.g. `ch01`).
        chapter_title: Chapter title.
        pdf_path: Optional chapter PDF path for `gemini_web`.
        backend: `gemini_web` (default) or `notebooklm` (fallback).
        model: Gemini model name (default `4 Argon`).
        notebook_id: NotebookLM ID when `backend == notebooklm`.
        source_ids: Single-chapter NotebookLM source IDs.
        steps_override: Optional list of step IDs for partial rerun.
    """

    course_key: str
    course_name: str
    chapter_id: str
    chapter_title: str = ""
    pdf_path: str = ""
    backend: NoteBackend = NoteBackend.GEMINI_WEB
    model: str = "4 Argon"
    notebook_id: str = ""
    source_ids: list[str] = Field(default_factory=list)
    steps_override: list[str] | None = None
    study_dir: str = ""


def _json_or_error(fn: Callable[[], Any], *, indent: int | None = None) -> str:
    """Run a note MCP call and serialize its result, turning validation errors into JSON errors.

    Args:
        fn: Zero-argument callable returning a JSON-serializable object.
        indent: Optional JSON indentation passed to `json.dumps`.

    Returns:
        Serialized JSON string (or `{"error": ...}` when input/path validation fails).
    """
    try:
        return json.dumps(fn(), ensure_ascii=False, indent=indent)
    except (PathSafetyError, FileNotFoundError, ValueError) as exc:
        logger.warning("Note MCP tool rejected request: %s", exc)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_prompt_tools(mcp: MCPServer, service: NotePipelineService) -> None:
    """Register prompt listing and preview MCP tools.

    Args:
        mcp: MCPServer instance.
        service: NotePipelineService instance.
    """

    @mcp.tool()
    def notes_list_prompts() -> str:
        """List standalone modular `.md` prompt templates and their file paths.

        Returns:
            JSON string with `prompts` array.
        """
        return json.dumps({"prompts": service.list_prompts()}, ensure_ascii=False, indent=2)

    @mcp.tool()
    def notes_preview_prompt(
        step_id: str,
        course_name: str,
        chapter_id: str,
        chapter_title: str = "",
    ) -> str:
        """Preview a modular `.md` prompt with chapter metadata filled in.

        Args:
            step_id: Step code such as `01_mindmap`.
            course_name: Course name.
            chapter_id: Chapter code such as `ch01`.
            chapter_title: Chapter title.

        Returns:
            JSON string containing the rendered prompt.
        """
        ctx = StepPromptContext(course_name, chapter_id, chapter_title)
        return json.dumps(service.preview_prompt(step_id, ctx), ensure_ascii=False, indent=2)


def _register_status_tools(mcp: MCPServer, service: NotePipelineService) -> None:
    """Register the note generation status MCP tool.

    Args:
        mcp: MCPServer instance.
        service: NotePipelineService instance.
    """

    @mcp.tool()
    def notes_get_status(course_key: str) -> str:
        """Get Phase 1 note generation status and pause state for a course.

        Args:
            course_key: Course identifier.

        Returns:
            JSON string of course state.
        """
        return _json_or_error(lambda: service.get_status(course_key), indent=2)


def _register_chapter_read_tools(mcp: MCPServer, service: NotePipelineService) -> None:
    """Register stitched-note reading and chapter listing MCP tools.

    Args:
        mcp: MCPServer instance.
        service: NotePipelineService instance.
    """

    @mcp.tool()
    def notes_read_chapter(course_key: str, chapter_id: str) -> str:
        """Read the stitched Markdown note for a chapter.

        Args:
            course_key: Course identifier.
            chapter_id: Chapter identifier.

        Returns:
            JSON string with `exists`, `path`, and `content`.
        """
        return _json_or_error(lambda: service.read_stitched_note(course_key, chapter_id))

    @mcp.tool()
    def notes_list_chapters(course_key: str) -> str:
        """List stitched chapter `.md` notes stored in `03 Notes/NoteStudio` or `scratch/notes`.

        Args:
            course_key: Course identifier.

        Returns:
            JSON string with `chapters` array.
        """
        return _json_or_error(lambda: {"chapters": service.list_chapters(course_key)}, indent=2)


def _register_note_file_tools(mcp: MCPServer, service: NotePipelineService) -> None:
    """Register read-only tools for every `.md` / `.pdf` in a course NoteStudio folder (Refs: SPEC-017).

    Args:
        mcp: MCPServer instance.
        service: NotePipelineService instance.
    """

    @mcp.tool()
    def notes_list_files(course_key: str) -> str:
        """List overview, PDF and module-draft note files, not only stitched chapters.

        Args:
            course_key: Course identifier.

        Returns:
            JSON string with `files` array (`relative_path`, `kind`, `size`, `is_chapter`).
        """
        return _json_or_error(
            lambda: {"files": list_note_files(service.paths.notes_course_dir(course_key))}, indent=2
        )

    @mcp.tool()
    def notes_read_file(course_key: str, relative_path: str) -> str:
        """Read one note file by its relative path (Markdown content; PDFs return their path).

        Args:
            course_key: Course identifier.
            relative_path: Path returned by `notes_list_files`.

        Returns:
            JSON string with `relative_path`, `kind`, `path`, `content`.
        """
        return _json_or_error(
            lambda: read_note_file(service.paths.notes_course_dir(course_key), relative_path)
        )


def _register_generate_tool(mcp: MCPServer, service: NotePipelineService) -> None:
    """Register the chapter note generation MCP tool.

    Args:
        mcp: MCPServer instance.
        service: NotePipelineService instance.
    """

    @mcp.tool()
    def notes_generate_chapter(params: McpNoteGenerateInput, confirm: bool = False) -> str:
        """Generate or rerun modular `.md` notes for one chapter (requires confirm=True).

        Args:
            params: Chapter generation configuration.
            confirm: Must be True to start generation.

        Returns:
            JSON string of generation outcome or confirmation prompt.
        """
        if not confirm:
            return _confirm_prompt("Call again with confirm=True to start chapter note generation.")
        req = ChapterNoteRequest(
            course_key=params.course_key,
            course_name=params.course_name,
            chapter_id=params.chapter_id,
            chapter_title=params.chapter_title,
            pdf_path=Path(params.pdf_path) if params.pdf_path else None,
            backend=params.backend,
            model=params.model,
            notebook_id=params.notebook_id,
            source_ids=list(params.source_ids),
            steps_override=params.steps_override,
            study_dir=Path(params.study_dir) if params.study_dir else None,
        )
        return _json_or_error(lambda: service.run_chapter(req), indent=2)


def _register_pause_tool(mcp: MCPServer, service: NotePipelineService) -> None:
    """Register the course pause MCP tool.

    Args:
        mcp: MCPServer instance.
        service: NotePipelineService instance.
    """

    @mcp.tool()
    def notes_pause_course(course_key: str, confirm: bool = False) -> str:
        """Request a clean pause for a course's note generation (requires confirm=True).

        Args:
            course_key: Course identifier.
            confirm: Must be True to persist pause request.

        Returns:
            JSON string of pause state.
        """
        if not confirm:
            return _confirm_prompt("Call again with confirm=True to pause note generation.")
        return _json_or_error(lambda: service.request_pause(course_key))


def _confirm_prompt(message: str) -> str:
    """Build the JSON reply asking the caller to repeat the call with `confirm=True`.

    Args:
        message: What to tell the caller.

    Returns:
        JSON string with `confirmed: False` and a `warning` message.
    """
    return json.dumps({"confirmed": False, "warning": message}, ensure_ascii=False)


def _register_push_tool(
    mcp: MCPServer,
    service: NotePipelineService,
    upload_fn: Callable[[str, str], str] | None,
) -> None:
    """Register the Phase 2 push-to-source MCP tool.

    Args:
        mcp: MCPServer instance.
        service: NotePipelineService instance.
        upload_fn: Optional callback `(notebook_id, pdf_path) -> source_id`.
    """

    @mcp.tool()
    def notes_push_to_source(
        course_key: str,
        chapter_id: str,
        notebook_id: str,
        confirm: bool = False,
    ) -> str:
        """Render a chapter `.md` note to PDF and upload to Gemini Notebook (requires confirm=True).

        Args:
            course_key: Course identifier.
            chapter_id: Chapter identifier (e.g. `ch01`).
            notebook_id: Target Gemini Notebook ID.
            confirm: Must be True to upload.

        Returns:
            JSON string with `source_id` or confirmation prompt.
        """
        if not confirm:
            return _confirm_prompt("Call again with confirm=True to upload chapter note PDF.")
        if upload_fn is None:
            return json.dumps({"error": "Upload adapter not configured."}, ensure_ascii=False)
        return _json_or_error(lambda: service.push_to_source(course_key, chapter_id, notebook_id, upload_fn))


def _register_legacy_import_tool(mcp: MCPServer, service: NotePipelineService) -> None:
    """Register the Phase 2 legacy note import MCP tool.

    Args:
        mcp: MCPServer instance.
        service: NotePipelineService instance.
    """

    @mcp.tool()
    def notes_import_legacy(
        source_dir: str,
        course_key: str,
        overwrite: bool = False,
        confirm: bool = False,
    ) -> str:
        """Import standalone `note-studio` `.md` notes into `03 Notes/NoteStudio` (requires confirm=True).

        Args:
            source_dir: Folder containing `.md` notes.
            course_key: Target course identifier.
            overwrite: Whether to overwrite existing files.
            confirm: Must be True to copy files.

        Returns:
            JSON string of import summary or confirmation prompt.
        """
        if not confirm:
            return _confirm_prompt("Call again with confirm=True to import legacy notes.")
        return _json_or_error(
            lambda: service.import_legacy(Path(source_dir), course_key, overwrite=overwrite)
        )


def register_note_pipeline_tools(
    mcp: MCPServer,
    service: NotePipelineService,
    upload_fn: Callable[[str, str], str] | None = None,
) -> None:
    """Register all Phase 1 & Phase 2 note pipeline MCP tools on `mcp`.

    Args:
        mcp: MCPServer instance.
        service: NotePipelineService instance.
        upload_fn: Optional callback `(notebook_id, pdf_path) -> source_id`.
    """
    _register_prompt_tools(mcp, service)
    _register_status_tools(mcp, service)
    _register_chapter_read_tools(mcp, service)
    _register_note_file_tools(mcp, service)
    _register_generate_tool(mcp, service)
    _register_pause_tool(mcp, service)
    _register_push_tool(mcp, service, upload_fn)
    _register_legacy_import_tool(mcp, service)
    logger.debug("Registered Phase 1 & 2 note pipeline MCP tools")

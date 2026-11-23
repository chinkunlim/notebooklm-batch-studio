"""MCP tools for Phase 1 modular Markdown note generation (Refs: ADR-012)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from notebooklm_batch_studio.domain.note_pipeline import NoteBackend
from notebooklm_batch_studio.services.notes.module_prompts import StepPromptContext
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
    """Register status and stitched-note reading MCP tools.

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
        return json.dumps(service.get_status(course_key), ensure_ascii=False, indent=2)

    @mcp.tool()
    def notes_read_chapter(course_key: str, chapter_id: str) -> str:
        """Read the stitched Markdown note for a chapter.

        Args:
            course_key: Course identifier.
            chapter_id: Chapter identifier.

        Returns:
            JSON string with `exists`, `path`, and `content`.
        """
        return json.dumps(service.read_stitched_note(course_key, chapter_id), ensure_ascii=False)

    @mcp.tool()
    def notes_list_chapters(course_key: str) -> str:
        """List stitched chapter `.md` notes stored in `03 Notes/NoteStudio` or `scratch/notes`.

        Args:
            course_key: Course identifier.

        Returns:
            JSON string with `chapters` array.
        """
        return json.dumps({"chapters": service.list_chapters(course_key)}, ensure_ascii=False, indent=2)


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
            return json.dumps(
                {"confirm": "Call again with confirm=True to start chapter note generation."},
                ensure_ascii=False,
            )
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
        return json.dumps(service.run_chapter(req), ensure_ascii=False, indent=2)


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
            return json.dumps(
                {"confirm": "Call again with confirm=True to pause note generation."},
                ensure_ascii=False,
            )
        return json.dumps(service.request_pause(course_key), ensure_ascii=False)


def _register_sync_tools(
    mcp: MCPServer,
    service: NotePipelineService,
    upload_fn: Callable[[str, str], str] | None,
) -> None:
    """Register Phase 2 push-to-source and legacy import MCP tools.

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
            return json.dumps(
                {"confirm": "Call again with confirm=True to upload chapter note PDF."},
                ensure_ascii=False,
            )
        if upload_fn is None:
            return json.dumps({"error": "Upload adapter not configured."}, ensure_ascii=False)
        return json.dumps(
            service.push_to_source(course_key, chapter_id, notebook_id, upload_fn),
            ensure_ascii=False,
        )

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
            return json.dumps(
                {"confirm": "Call again with confirm=True to import legacy notes."},
                ensure_ascii=False,
            )
        return json.dumps(
            service.import_legacy(Path(source_dir), course_key, overwrite=overwrite),
            ensure_ascii=False,
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
    _register_generate_tool(mcp, service)
    _register_pause_tool(mcp, service)
    _register_sync_tools(mcp, service, upload_fn)
    logger.debug("Registered Phase 1 & 2 note pipeline MCP tools")

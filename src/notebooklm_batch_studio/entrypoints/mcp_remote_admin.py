"""MCP tools for advanced remote Gemini Notebook artifact operations."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from notebooklm_batch_studio.entrypoints.schemas import (
    ChatConfigureRequest,
    ExportArtifactRequest,
    GenerateScopedArtifactRequest,
    ReviseSlideRequest,
)
from notebooklm_batch_studio.services.remote_admin_service import RemoteAdminService

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer


def register_remote_extra_tools(mcp: MCPServer, service: Any) -> None:
    """Register cinematic video, slide revision, export, suggest, and retry MCP tools.

    Args:
        mcp: FastMCP server instance.
        service: BatchStudioService instance.
    """
    admin = RemoteAdminService(service.course_repo, service.notebooklm_client)
    _reg_suggest_tool(mcp, admin)
    _reg_cinematic_tool(mcp, admin)
    _reg_revise_slide_tool(mcp, admin)
    _reg_export_tool(mcp, admin)
    _reg_retry_tool(mcp, admin)
    _reg_add_url_tool(mcp, admin)
    _reg_add_text_tool(mcp, admin)
    _reg_research_discover_tool(mcp, admin)
    _reg_research_import_tool(mcp, admin)
    _reg_chat_config_tool(mcp, admin)
    _reg_scoped_generate_tool(mcp, admin)


def _reg_suggest_tool(mcp: MCPServer, admin: RemoteAdminService) -> None:
    """Register suggest_course_reports tool.

    Args:
        mcp: FastMCP server instance.
        admin: RemoteAdminService instance.
    """

    @mcp.tool()
    async def suggest_course_reports(course_code: str) -> str:
        """Ask Gemini Notebook for AI-suggested report topics.

        Args:
            course_code: Course identifier.

        Returns:
            JSON string with suggested reports.
        """
        return json.dumps(await admin.suggest_reports(course_code), ensure_ascii=False, indent=2)


def _reg_cinematic_tool(mcp: MCPServer, admin: RemoteAdminService) -> None:
    """Register generate_cinematic_video tool.

    Args:
        mcp: FastMCP server instance.
        admin: RemoteAdminService instance.
    """

    @mcp.tool()
    async def generate_cinematic_video(
        course_code: str, instructions: str = "", lecture_no: int | None = None, confirm: bool = False
    ) -> str:
        """Generate a cinematic video overview in Gemini Notebook.

        Args:
            course_code: Course identifier.
            instructions: Focus prompt instructions.
            lecture_no: Optional lecture number filter.
            confirm: Must be True to trigger remote generation.

        Returns:
            JSON string with generation result or confirmation warning.
        """
        if not confirm:
            return json.dumps({"requires_confirmation": True, "action": "generate_cinematic_video"})
        res = await admin.generate_cinematic_video(course_code, instructions, lecture_no)
        return json.dumps(res, ensure_ascii=False, indent=2)


def _reg_revise_slide_tool(mcp: MCPServer, admin: RemoteAdminService) -> None:
    """Register revise_remote_slide tool.

    Args:
        mcp: FastMCP server instance.
        admin: RemoteAdminService instance.
    """

    @mcp.tool()
    async def revise_remote_slide(
        course_code: str, artifact_id: str, payload: ReviseSlideRequest, confirm: bool = False
    ) -> str:
        """Revise a single slide in an existing slide deck artifact.

        Args:
            course_code: Course identifier.
            artifact_id: Slide deck artifact identifier.
            payload: Zero-based slide index and revision prompt.
            confirm: Must be True to execute revision.

        Returns:
            JSON string with revision result or confirmation warning.
        """
        if not confirm:
            return json.dumps({"requires_confirmation": True, "artifact_id": artifact_id})
        res = await admin.revise_slide(course_code, artifact_id, payload.slide_index, payload.prompt)
        return json.dumps(res, ensure_ascii=False, indent=2)


def _reg_export_tool(mcp: MCPServer, admin: RemoteAdminService) -> None:
    """Register export_remote_artifact tool.

    Args:
        mcp: FastMCP server instance.
        admin: RemoteAdminService instance.
    """

    @mcp.tool()
    async def export_remote_artifact(
        course_code: str, artifact_id: str, payload: ExportArtifactRequest, confirm: bool = False
    ) -> str:
        """Export a report or data table to Google Docs or Sheets.

        Args:
            course_code: Course identifier.
            artifact_id: Remote artifact identifier.
            payload: Export title and artifact kind.
            confirm: Must be True to execute export.

        Returns:
            JSON string with export result or confirmation warning.
        """
        if not confirm:
            return json.dumps({"requires_confirmation": True, "artifact_id": artifact_id})
        res = await admin.export_artifact(course_code, artifact_id, title=payload.title, kind=payload.kind)
        return json.dumps(res, ensure_ascii=False, indent=2)


def _reg_retry_tool(mcp: MCPServer, admin: RemoteAdminService) -> None:
    """Register retry_remote_artifact tool.

    Args:
        mcp: FastMCP server instance.
        admin: RemoteAdminService instance.
    """

    @mcp.tool()
    async def retry_remote_artifact(course_code: str, artifact_id: str, confirm: bool = False) -> str:
        """Retry a failed remote artifact directly on Gemini Notebook.

        Args:
            course_code: Course identifier.
            artifact_id: Failed artifact identifier.
            confirm: Must be True to trigger remote retry.

        Returns:
            JSON string with retry status or confirmation warning.
        """
        if not confirm:
            return json.dumps({"requires_confirmation": True, "artifact_id": artifact_id})
        res = await admin.retry_remote_artifact(course_code, artifact_id)
        return json.dumps(res, ensure_ascii=False, indent=2)


def _reg_add_url_tool(mcp: MCPServer, admin: RemoteAdminService) -> None:
    """Register add_url_source MCP tool.

    Args:
        mcp: FastMCP server instance.
        admin: RemoteAdminService instance.
    """

    @mcp.tool()
    async def add_url_source(
        course_code: str, url: str, title: str | None = None, confirm: bool = False
    ) -> str:
        """Add a web or YouTube URL source to a course notebook.

        Args:
            course_code: Course identifier.
            url: Web page or YouTube URL.
            title: Optional custom title for the source.
            confirm: Must be True to add remote source.

        Returns:
            JSON string with created source or confirmation prompt.
        """
        if not confirm:
            return json.dumps({"requires_confirmation": True, "url": url})
        res = await admin.add_url_source(course_code, url, title=title)
        return json.dumps(res, ensure_ascii=False, indent=2)


def _reg_add_text_tool(mcp: MCPServer, admin: RemoteAdminService) -> None:
    """Register add_text_source MCP tool.

    Args:
        mcp: FastMCP server instance.
        admin: RemoteAdminService instance.
    """

    @mcp.tool()
    async def add_text_source(course_code: str, title: str, content: str, confirm: bool = False) -> str:
        """Add pasted plain text as a source in a course notebook.

        Args:
            course_code: Course identifier.
            title: Source title.
            content: Plain text content.
            confirm: Must be True to add remote source.

        Returns:
            JSON string with created source or confirmation prompt.
        """
        if not confirm:
            return json.dumps({"requires_confirmation": True, "title": title})
        res = await admin.add_text_source(course_code, title, content)
        return json.dumps(res, ensure_ascii=False, indent=2)


def _reg_research_discover_tool(mcp: MCPServer, admin: RemoteAdminService) -> None:
    """Register research_course_sources MCP tool.

    Args:
        mcp: FastMCP server instance.
        admin: RemoteAdminService instance.
    """

    @mcp.tool()
    async def research_course_sources(course_code: str, query: str, mode: str = "fast") -> str:
        """Run web discovery research in a course notebook.

        Args:
            course_code: Course identifier.
            query: Search topic or question.
            mode: Discovery mode ('fast' or 'deep').

        Returns:
            JSON string with discovered sources and task_id.
        """
        res = await admin.research_sources(course_code, query, mode=mode)
        return json.dumps(res, ensure_ascii=False, indent=2)


def _reg_research_import_tool(mcp: MCPServer, admin: RemoteAdminService) -> None:
    """Register import_research_sources MCP tool.

    Args:
        mcp: FastMCP server instance.
        admin: RemoteAdminService instance.
    """

    @mcp.tool()
    async def import_research_sources(
        course_code: str, task_id: str, sources: list[dict[str, str]], confirm: bool = False
    ) -> str:
        """Import selected research sources into a course notebook.

        Args:
            course_code: Course identifier.
            task_id: Discovery task identifier.
            sources: Selected source dicts containing url and title.
            confirm: Must be True to import sources.

        Returns:
            JSON string with import summary or confirmation prompt.
        """
        if not confirm:
            return json.dumps({"requires_confirmation": True, "task_id": task_id})
        res = await admin.import_research_sources(course_code, task_id, sources)
        return json.dumps(res, ensure_ascii=False, indent=2)


def _reg_chat_config_tool(mcp: MCPServer, admin: RemoteAdminService) -> None:
    """Register configure_notebook_chat MCP tool.

    Args:
        mcp: FastMCP server instance.
        admin: RemoteAdminService instance.
    """

    @mcp.tool()
    async def configure_notebook_chat(
        course_code: str,
        settings: ChatConfigureRequest,
        confirm: bool = False,
    ) -> str:
        """Configure Gemini Notebook chat goal and response length.

        Args:
            course_code: Course identifier.
            settings: ChatConfigureRequest containing goal, response_length, and custom_prompt.
            confirm: Must be True to update remote notebook settings.

        Returns:
            JSON string with applied settings or confirmation prompt.
        """
        if not confirm:
            return json.dumps({"requires_confirmation": True, "goal": settings.goal})
        res = await admin.configure_chat(
            course_code,
            goal=settings.goal,
            response_length=settings.response_length,
            custom_prompt=settings.custom_prompt,
        )
        return json.dumps(res, ensure_ascii=False, indent=2)


def _reg_scoped_generate_tool(mcp: MCPServer, admin: RemoteAdminService) -> None:
    """Register generate_from_sources MCP tool.

    Args:
        mcp: FastMCP server instance.
        admin: RemoteAdminService instance.
    """

    @mcp.tool()
    async def generate_from_sources(
        course_code: str, payload: GenerateScopedArtifactRequest, confirm: bool = False
    ) -> str:
        """Generate a Studio artifact or custom report for selected source IDs.

        Args:
            course_code: Course identifier.
            payload: Artifact kind, optional source_ids, and instructions.
            confirm: Must be True to trigger remote generation.

        Returns:
            JSON string with created artifact_id or confirmation prompt.
        """
        if not confirm:
            return json.dumps({"requires_confirmation": True, "kind": payload.kind})
        res = await admin.generate_from_sources(
            course_code,
            payload.kind,
            {"source_ids": payload.source_ids, "instructions": payload.instructions},
        )
        return json.dumps(res, ensure_ascii=False, indent=2)

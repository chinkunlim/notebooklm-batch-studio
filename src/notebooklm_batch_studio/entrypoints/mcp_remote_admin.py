"""MCP tools for advanced remote Gemini Notebook artifact operations."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from notebooklm_batch_studio.entrypoints.schemas import ExportArtifactRequest, ReviseSlideRequest
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

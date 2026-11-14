"""MCP tools for one output's own settings and for course administration (pause, start, delete)."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.services.orchestrator import BatchStudioService


def _set_job_options_payload(
    active_service: BatchStudioService, job_id: str, options: dict[str, Any], confirm: bool
) -> str:
    """Validate confirmation flag and apply per-job generation options.

    Args:
        active_service: Orchestrator service.
        job_id: Target job identifier.
        options: Option overrides dictionary.
        confirm: Explicit confirmation flag.

    Returns:
        JSON string response.
    """
    if not confirm:
        return json.dumps(
            {"confirmed": False, "warning": "Set confirm=True to save.", "options": options},
            ensure_ascii=False,
        )
    try:
        return json.dumps(active_service.course_settings.set_job_options(job_id, options), ensure_ascii=False)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _set_course_paused_payload(
    active_service: BatchStudioService, code: str, paused: bool, confirm: bool
) -> str:
    """Pause or unpause a course and start the queue when resumed.

    Args:
        active_service: Orchestrator service.
        code: Course code.
        paused: Target pause state.
        confirm: Explicit confirmation flag.

    Returns:
        JSON string response.
    """
    if not confirm:
        return json.dumps({"confirmed": False, "warning": "Set confirm=True to apply."}, ensure_ascii=False)
    try:
        result = active_service.course_settings.set_paused(code, paused)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    if not paused:
        active_service.start_queue()
    return json.dumps(result, ensure_ascii=False)


def _delete_course_payload(active_service: BatchStudioService, code: str, confirm: bool) -> str:
    """Delete a course from local DB and move outputs to deleted archive.

    Args:
        active_service: Orchestrator service.
        code: Course code.
        confirm: Explicit confirmation flag.

    Returns:
        JSON string response.
    """
    if not confirm:
        return json.dumps(
            {"confirmed": False, "warning": "Set confirm=True to delete this course's local records."},
            ensure_ascii=False,
        )
    try:
        return json.dumps(active_service.course_settings.delete_course(code), ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _copy_course_options_payload(
    active_service: BatchStudioService, code: str, targets: list[str], confirm: bool
) -> str:
    """Copy course options from one source course to target courses.

    Args:
        active_service: Orchestrator service.
        code: Source course code.
        targets: Target course codes.
        confirm: Explicit confirmation flag.

    Returns:
        JSON string response.
    """
    if not confirm:
        return json.dumps(
            {
                "confirmed": False,
                "warning": "Set confirm=True to overwrite target courses' options.",
                "source": code,
                "targets": targets,
            },
            ensure_ascii=False,
        )
    try:
        res = active_service.course_settings.copy_options(code, targets)
        res["confirmed"] = True
        return json.dumps(res, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def register_course_settings_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register per-output setting tools and course admin tools (changes require confirm=True).

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """
    _register_job_option_tools(mcp, active_service)
    _register_course_admin_tools(mcp, active_service)


def _register_job_option_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register tools for one output's own generation settings (SPEC-006).

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def get_job_options(job_id: str) -> str:
        """Read one output's own settings and the settings it will actually use (read-only).

        Args:
            job_id: Job id (from get_course_status).

        Returns:
            JSON string with overrides, effective options and supported fields.
        """
        try:
            data = active_service.course_settings.get_job_options(job_id)
            return json.dumps(data, ensure_ascii=False, indent=2)
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def set_job_options(job_id: str, options: dict[str, Any], confirm: bool = False) -> str:
        """Set one output's own settings, e.g. {"quiz_questions": 20} (requires confirm=True).

        Args:
            job_id: Job id.
            options: Option overrides; "" removes one and falls back to the course setting.
            confirm: Must be True to save.

        Returns:
            JSON string with the updated settings, or a confirmation warning.
        """
        return _set_job_options_payload(active_service, job_id, options, confirm)


def _register_course_admin_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register per-course pause / start, deletion, and option-copy tools (all require confirm).

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """
    _register_pause_and_delete_tools(mcp, active_service)
    _register_copy_options_tool(mcp, active_service)


def _register_pause_and_delete_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register per-course pause / start and deletion MCP tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def set_course_paused(code: str, paused: bool, confirm: bool = False) -> str:
        """Pause a course (jobs wait) or start it (jobs run; spends quota). Requires confirm=True.

        Args:
            code: Course code.
            paused: True to pause, False to start.
            confirm: Must be True to apply.

        Returns:
            JSON string with the new state, or a confirmation warning.
        """
        return _set_course_paused_payload(active_service, code, paused, confirm)

    @mcp.tool()
    def delete_course(code: str, confirm: bool = False) -> str:
        """Remove a course from this app; outputs move to DATA_DIR/deleted/, Gemini Notebook untouched.

        Args:
            code: Course code.
            confirm: Must be True to delete.

        Returns:
            JSON string with what was removed and moved, or a confirmation warning.
        """
        return _delete_course_payload(active_service, code, confirm)


def _register_copy_options_tool(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register copy-course-options MCP tool.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def copy_course_options(code: str, targets: list[str], confirm: bool = False) -> str:
        """Copy one course's generation options, language, and mock exam count to other courses.

        Args:
            code: Source course code.
            targets: Target course codes to overwrite.
            confirm: Must be True to overwrite target course settings.

        Returns:
            JSON string with copied targets and values, or a confirmation warning.
        """
        return _copy_course_options_payload(active_service, code, targets, confirm)

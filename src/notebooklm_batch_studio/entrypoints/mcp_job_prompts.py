"""MCP tools to read and change the prompt one job sends to Gemini Notebook."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.entrypoints.mcp_confirm import confirm_warning
from notebooklm_batch_studio.services.orchestrator import BatchStudioService


def _register_prompt_tools(mcp: MCPServer, service: BatchStudioService) -> None:
    """Register get_job_prompt (read-only) and set_job_prompt (requires confirm=True).

    Args:
        mcp: MCPServer instance.
        service: Orchestrator service.
    """

    @mcp.tool()
    def get_job_prompt(job_id: str) -> str:
        """Show the prompt a job sends to Gemini Notebook (read-only).

        Args:
            job_id: Job id.

        Returns:
            JSON string with job_id and custom_prompt, or an error.
        """
        job = service.queue_repo.get_job(job_id)
        if job is None:
            return json.dumps({"error": f"Job not found: {job_id}"}, ensure_ascii=False)
        return json.dumps({"job_id": job.id, "custom_prompt": job.custom_prompt}, ensure_ascii=False)

    @mcp.tool()
    def set_job_prompt(job_id: str, prompt: str, confirm: bool = False) -> str:
        """Replace a job's prompt (requires confirm=True; affects the next run or regeneration).

        Args:
            job_id: Job id.
            prompt: New prompt text.
            confirm: Must be True to save.

        Returns:
            JSON string with confirmed / success flags.
        """
        if not confirm:
            return confirm_warning("Pass confirm=True to save the prompt.")
        ok = service.update_job_prompt(job_id, prompt)
        return json.dumps({"confirmed": True, "success": ok}, ensure_ascii=False)


def _register_retry_failed_tool(mcp: MCPServer, service: BatchStudioService) -> None:
    """Register retry_course_failed_jobs MCP tool (requires confirm=True).

    Args:
        mcp: MCPServer instance.
        service: Orchestrator service.
    """

    @mcp.tool()
    def retry_course_failed_jobs(
        course_code: str, include_needs_review: bool = True, confirm: bool = False
    ) -> str:
        """Re-queue all failed (and optionally needs_review) jobs for a course (requires confirm=True).

        Args:
            course_code: Course code.
            include_needs_review: Whether to also retry NEEDS_REVIEW jobs.
            confirm: Must be True to re-queue failed jobs.

        Returns:
            JSON string with confirmed status and retried_count, or an error.
        """
        if not confirm:
            return confirm_warning("Pass confirm=True to retry failed jobs.")
        try:
            count = service.retry_course_failed_jobs(course_code, include_needs_review=include_needs_review)
        except CourseNotFoundError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        return json.dumps(
            {"confirmed": True, "course_code": course_code, "retried_count": count}, ensure_ascii=False
        )


def register_job_prompt_tools(mcp: MCPServer, service: BatchStudioService) -> None:
    """Register job prompt inspection, mutation, and course failed-job retry tools.

    Args:
        mcp: MCPServer instance.
        service: Orchestrator service.
    """
    _register_prompt_tools(mcp, service)
    _register_retry_failed_tool(mcp, service)

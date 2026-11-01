"""MCP tools to read and change the prompt one job sends to Gemini Notebook."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.services.orchestrator import BatchStudioService


def register_job_prompt_tools(mcp: MCPServer, service: BatchStudioService) -> None:
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
            return json.dumps({"confirmed": False, "message": "Pass confirm=True to save the prompt."})
        ok = service.update_job_prompt(job_id, prompt)
        return json.dumps({"confirmed": True, "success": ok}, ensure_ascii=False)

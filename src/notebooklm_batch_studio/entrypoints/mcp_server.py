"""Model Context Protocol (MCP) server for NotebookLM Batch Studio.

Exposes tools for Agent pairing (Claude Code, Antigravity, OpenCode, Open WebUI)
to monitor course progress, preview imports, enqueue batches, view quizzes, and retry jobs.
Mutating operations strictly enforce the `confirm: bool` safety protocol.
"""

from __future__ import annotations

import asyncio
import json
import logging

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.config.logging_setup import setup_logging
from notebooklm_batch_studio.config.settings import AppConfig, load_config
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

logger = logging.getLogger(__name__)


def _register_course_query_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register course querying tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def list_courses() -> str:
        """List all registered courses, progress completion, and NotebookLM links.

        Returns:
            JSON string containing course summaries.
        """
        summaries = active_service.get_courses_summary()
        return json.dumps(summaries, ensure_ascii=False, indent=2)

    @mcp.tool()
    def get_course_status(course_code: str) -> str:
        """Get lecture breakdown and artifact generation state for a course.

        Args:
            course_code: Course code identifier (e.g. 'BIO101').

        Returns:
            JSON string containing course details and job records.
        """
        try:
            detail = active_service.get_course_detail(course_code)
            return json.dumps(detail, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_artifact_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register artifact and quiz querying tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def get_quiz(
        course_code: str,
        lecture_no: int,
        variant: str = "1-基礎",
        with_answers: bool = False,
    ) -> str:
        """Retrieve generated quiz questions for a lecture.

        Args:
            course_code: Course identifier.
            lecture_no: Sequence number of lecture.
            variant: Quiz variant ('1-基礎', '2-理解', '3-模擬考').
            with_answers: If False, question sheet only; if True, includes rationales and answers.

        Returns:
            Markdown text of the quiz.
        """
        try:
            result = active_service.get_quiz_content(
                course_code, lecture_no, variant, with_answers=with_answers
            )
            return str(result["markdown"])
        except Exception as exc:
            return f"Error retrieving quiz: {exc}"

    @mcp.tool()
    def get_artifact_files(course_code: str, lecture_no: int | None = None) -> str:
        """List generated deliverable files present on disk for a course.

        Args:
            course_code: Course identifier.
            lecture_no: Optional sequence number to filter files by lecture.

        Returns:
            JSON string of file records and download paths.
        """
        files = active_service.list_artifact_files(course_code, lecture_no=lecture_no)
        return json.dumps(files, ensure_ascii=False, indent=2)


def _register_import_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register course import and preview tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def preview_add_courses(folders: list[str]) -> str:
        """Preview lecture extraction and workload estimation for course folders.

        Args:
            folders: List of filesystem paths to candidate course folders.

        Returns:
            JSON string describing detected lectures and estimated jobs.
        """
        preview = active_service.preview_course_folders(folders)
        return json.dumps(preview, ensure_ascii=False, indent=2)

    @mcp.tool()
    def add_courses(folders: list[str], profile: str = "full", confirm: bool = False) -> str:
        """Register course folders and enqueue generation jobs (requires confirm=True).

        Args:
            folders: List of filesystem paths to course folders.
            profile: Artifact profile ('full', 'quiz-only', 'exam-prep').
            confirm: Must be explicitly set to True to execute database modifications.

        Returns:
            Result summary or confirmation preview message.
        """
        if not confirm:
            preview = active_service.preview_course_folders(folders)
            return json.dumps(
                {
                    "confirmed": False,
                    "warning": "Action not confirmed. Set confirm=True to persist and enqueue.",
                    "preview": preview,
                },
                ensure_ascii=False,
                indent=2,
            )

        registered = active_service.add_course_folders(folders, profile=profile)
        return json.dumps(
            {
                "confirmed": True,
                "message": f"Successfully registered {len(registered)} courses.",
                "courses": registered,
            },
            ensure_ascii=False,
            indent=2,
        )


def _register_queue_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register queue control tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def start_queue(confirm: bool = False) -> str:
        """Start parallel worker task queue (requires confirm=True).

        Args:
            confirm: Must be explicitly set to True to start execution.

        Returns:
            Action result description.
        """
        if not confirm:
            return "Action not confirmed. Pass confirm=True to start worker processing."
        active_service.start_queue()
        return "Worker queue started successfully."

    @mcp.tool()
    def pause_queue(confirm: bool = False) -> str:
        """Pause worker task execution (requires confirm=True).

        Args:
            confirm: Must be explicitly set to True to pause execution.

        Returns:
            Action result description.
        """
        if not confirm:
            return "Action not confirmed. Pass confirm=True to pause worker processing."
        active_service.pause_queue()
        return "Worker queue paused successfully."


def _register_maintenance_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register retry and profile mutation tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def retry_item(job_id: str, confirm: bool = False) -> str:
        """Reset a failed task back to pending (requires confirm=True).

        Args:
            job_id: Task UUID to retry.
            confirm: Must be explicitly set to True to perform the retry.

        Returns:
            Action result message.
        """
        if not confirm:
            return f"Action not confirmed. Pass confirm=True to retry job {job_id}."
        success = active_service.retry_job(job_id)
        if success:
            return f"Job {job_id} successfully reset to pending."
        return f"Job {job_id} not found."

    @mcp.tool()
    def set_course_profile(course_code: str, profile: str, confirm: bool = False) -> str:
        """Update active profile for a course (requires confirm=True).

        Args:
            course_code: Course code identifier.
            profile: Target profile ('full', 'quiz-only', 'exam-prep').
            confirm: Must be set to True to commit the profile update.

        Returns:
            Result JSON or confirmation prompt.
        """
        if not confirm:
            return (
                f"Action not confirmed. Pass confirm=True to update course {course_code} "
                f"profile to '{profile}'."
            )
        try:
            res = active_service.set_course_profile(course_code, profile)
            return json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def build_mcp_server(
    service: BatchStudioService | None = None,
    config: AppConfig | None = None,
) -> MCPServer:
    """Build and configure the MCPServer instance with all batch studio tools.

    Args:
        service: Optional pre-configured BatchStudioService instance.
        config: Application configuration.

    Returns:
        Configured MCPServer with registered tool handlers.
    """
    cfg = config or load_config()

    if service is None:
        engine = create_db_engine(cfg.database_url)
        with session_scope(engine) as session:
            course_repo = CourseRepository(session)
            queue_repo = QueueRepository(session)
            adapter = NotebookLMAdapter(cfg)
            active_service = BatchStudioService(
                course_repo=course_repo,
                queue_repo=queue_repo,
                notebooklm_client=adapter,
                config=cfg,
            )
    else:
        active_service = service

    mcp = MCPServer("notebooklm-batch-studio")
    _register_course_query_tools(mcp, active_service)
    _register_artifact_tools(mcp, active_service)
    _register_import_tools(mcp, active_service)
    _register_queue_tools(mcp, active_service)
    _register_maintenance_tools(mcp, active_service)
    return mcp


def main() -> None:
    """Run the MCP server over stdio for Agent connections."""
    config = load_config()
    setup_logging(config.log_level, config.logs_dir if config.log_to_file else None)
    logger.info("Starting MCP stdio server for notebooklm-batch-studio")
    server = build_mcp_server(config=config)
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()

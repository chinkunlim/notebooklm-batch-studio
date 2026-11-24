"""Model Context Protocol (MCP) server for Gemini Notebook 學習工作室.

Exposes tools for Agent pairing (Claude Code, Antigravity, OpenCode, Open WebUI)
to monitor course progress, preview imports, enqueue batches, view quizzes, and retry jobs.
Mutating operations strictly enforce the `confirm: bool` safety protocol.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.adapters.db.learning_repository import LearningRepository
from notebooklm_batch_studio.adapters.db.notes_repository import QANoteRepository
from notebooklm_batch_studio.adapters.db.preferences_repository import PreferencesRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.review_repository import ReviewRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.adapters.fonts.google_fonts import GoogleFontsClient
from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.adapters.ollama.client import OllamaClient
from notebooklm_batch_studio.adapters.web_search import search_web_snippets
from notebooklm_batch_studio.config.logging_setup import setup_logging
from notebooklm_batch_studio.config.settings import AppConfig, load_config
from notebooklm_batch_studio.entrypoints.mcp_confirm import confirm_warning
from notebooklm_batch_studio.entrypoints.mcp_course_settings import register_course_settings_tools
from notebooklm_batch_studio.entrypoints.mcp_extensions import register_literature_and_note_tools
from notebooklm_batch_studio.entrypoints.mcp_fonts import register_font_tools
from notebooklm_batch_studio.entrypoints.mcp_job_prompts import register_job_prompt_tools
from notebooklm_batch_studio.entrypoints.mcp_learning import register_learning_tools
from notebooklm_batch_studio.entrypoints.mcp_preferences import register_preferences_tools
from notebooklm_batch_studio.entrypoints.mcp_qa_notes import (
    register_qa_notes_tools,
    register_remote_artifact_tools,
)
from notebooklm_batch_studio.entrypoints.mcp_studio_tools import register_settings_and_study_tools
from notebooklm_batch_studio.entrypoints.mcp_study_plan import register_study_plan_tools
from notebooklm_batch_studio.services.font_service import FontService
from notebooklm_batch_studio.services.learning_service import LearningService
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.preferences_service import PreferencesService
from notebooklm_batch_studio.services.qa_notes_service import QANotesService
from notebooklm_batch_studio.services.study_plan_service import StudyPlanDeps, StudyPlanService
from notebooklm_batch_studio.services.study_service import StudyTrackerService

logger = logging.getLogger(__name__)


async def _add_courses_payload(
    active_service: BatchStudioService, folders: list[str], profile: str, confirm: bool
) -> str:
    """Preview or register course folders depending on confirmation flag.

    Args:
        active_service: Orchestrator service.
        folders: List of candidate folder paths.
        profile: Selected generation profile string.
        confirm: Explicit confirmation flag.

    Returns:
        JSON string response.
    """
    if not confirm:
        preview = await active_service.preview_course_folders(folders)
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


async def _sync_remote_payload(active_service: BatchStudioService, course_code: str, confirm: bool) -> str:
    """Synchronize remote Gemini Notebook artifacts when confirmed.

    Args:
        active_service: Orchestrator service.
        course_code: Course identifier.
        confirm: Explicit confirmation flag.

    Returns:
        JSON string response.
    """
    if not confirm:
        return confirm_warning(
            f"Action not confirmed. Pass confirm=True to sync remote Gemini Notebook "
            f"artifacts for course '{course_code}'."
        )
    try:
        res = await active_service.sync_course_artifacts(course_code)
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _refine_prompts_payload(active_service: BatchStudioService, course_code: str, confirm: bool) -> str:
    """Refine pending job prompts with Ollama when confirmed.

    Args:
        active_service: Orchestrator service.
        course_code: Course identifier.
        confirm: Explicit confirmation flag.

    Returns:
        JSON string response.
    """
    if not confirm:
        return confirm_warning(
            f"Action not confirmed. Pass confirm=True to refine prompts using "
            f"Ollama for course '{course_code}'."
        )
    try:
        count = active_service.refine_course_prompts_with_ollama(course_code)
        return json.dumps(
            {
                "course_code": course_code,
                "refined_count": count,
                "message": f"Successfully refined {count} prompts using Ollama.",
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_course_list_and_quota_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register list_courses and get_notebooklm_quota tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def list_courses() -> str:
        """List all registered courses, progress completion, and Gemini Notebook links.

        Returns:
            JSON string containing course summaries.
        """
        return json.dumps(active_service.get_courses_summary(), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def get_notebooklm_quota() -> str:
        """Read the live Gemini Notebook usage meter and account limits (read-only).

        Returns:
            JSON string with 5-hour/weekly window usage and account limits.
        """
        try:
            return json.dumps(await active_service.get_notebooklm_quota(), ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_course_status_tool(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register get_course_status tool.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def get_course_status(course_code: str) -> str:
        """Get lecture breakdown and artifact generation state for a course.

        Args:
            course_code: Course code identifier (e.g. 'BIO101').

        Returns:
            JSON string containing course details and job records.
        """
        try:
            return json.dumps(active_service.get_course_detail(course_code), ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_quiz_read_tool(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register get_quiz read tool.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def get_quiz(
        course_code: str, lecture_no: int, variant: str = "1-基礎", with_answers: bool = False
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
            res = active_service.get_quiz_content(course_code, lecture_no, variant, with_answers=with_answers)
            return str(res["markdown"])
        except Exception as exc:
            return f"Error retrieving quiz: {exc}"


def _register_artifact_list_tool(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register get_artifact_files read tool.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

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
    async def preview_add_courses(folders: list[str]) -> str:
        """Preview lecture extraction and workload estimation for course folders.

        Args:
            folders: List of filesystem paths to candidate course folders.

        Returns:
            JSON string describing detected lectures and estimated jobs.
        """
        preview = await active_service.preview_course_folders(folders)
        return json.dumps(preview, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def add_courses(folders: list[str], profile: str = "full", confirm: bool = False) -> str:
        """Register course folders and enqueue generation jobs (requires confirm=True).

        Args:
            folders: List of filesystem paths to course folders.
            profile: Artifact profile ('full', 'quiz-only', 'exam-prep').
            confirm: Must be explicitly set to True to execute database modifications.

        Returns:
            Result summary or confirmation preview message.
        """
        return await _add_courses_payload(active_service, folders, profile, confirm)


def _register_queue_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register queue start and pause control tools.

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
            return confirm_warning("Action not confirmed. Pass confirm=True to start worker processing.")
        active_service.start_queue()
        return "Worker queue started successfully."

    @mcp.tool()
    def pause_queue(confirm: bool = False) -> str:
        """Pause worker task execution (requires confirm=True).

        Args:
            confirm: Must be explicitly set to True to pause execution.

        Returns:
            Action result description or confirmation JSON.
        """
        if not confirm:
            return confirm_warning("Action not confirmed. Pass confirm=True to pause worker processing.")
        active_service.pause_queue()
        return "Worker queue paused successfully."


def _register_retry_tool(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register the retry_item MCP tool.

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
            Action result message or confirmation JSON.
        """
        if not confirm:
            return confirm_warning(f"Action not confirmed. Pass confirm=True to retry job {job_id}.")
        if active_service.retry_job(job_id):
            return f"Job {job_id} successfully reset to pending."
        return f"Job {job_id} not found."


def _register_sync_and_prompt_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register remote sync and Ollama prompt refinement tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    async def sync_course_remote_artifacts(course_code: str, confirm: bool = False) -> str:
        """Synchronize manually generated Gemini Notebook artifacts to local storage (needs confirm=True).

        Args:
            course_code: Course identifier (e.g. 'BIO101').
            confirm: Must be set to True to execute remote download and database registration.

        Returns:
            JSON string describing synchronized items and count.
        """
        return await _sync_remote_payload(active_service, course_code, confirm)

    @mcp.tool()
    def refine_prompts_with_ollama(course_code: str, confirm: bool = False) -> str:
        """Refine pending job prompts for a course using Ollama (requires confirm=True).

        Args:
            course_code: Course identifier (e.g. 'BIO101').
            confirm: Must be True to execute Ollama prompt refinement.

        Returns:
            JSON string with updated job count.
        """
        return _refine_prompts_payload(active_service, course_code, confirm)


def _resolve_mcp_services(
    service: BatchStudioService | None, cfg: AppConfig, overrides: dict[str, Any]
) -> dict[str, Any]:
    """Resolve explicit or database-backed service instances for MCP tool registration.

    Args:
        service: Optional pre-configured BatchStudioService instance.
        cfg: Resolved AppConfig instance.
        overrides: Optional injected services (`study_service`, `study_plan`, `learning`, `preferences`,
            and `fonts`).

    Returns:
        Dictionary with `service`, `study_service`, `study_plan`, `learning`, `preferences`, and `fonts`.
    """
    study_service = overrides.get("study_service")
    if service is not None and study_service is not None:
        return {"service": service, "study_service": study_service, **overrides}

    engine = create_db_engine(cfg.database_url)
    with session_scope(engine) as session:
        c_repo, q_repo, s_repo = CourseRepository(session), QueueRepository(session), StudyRepository(session)
        adapter, ollama = NotebookLMAdapter(cfg), OllamaClient(config=cfg)
        active_service = service or BatchStudioService(c_repo, q_repo, adapter, cfg, ollama_client=ollama)
        active_study = study_service or StudyTrackerService(study_repo=s_repo, config=cfg, course_repo=c_repo)
        deps = StudyPlanDeps(c_repo, q_repo, s_repo, ReviewRepository(session), adapter)
        plan = overrides.get("study_plan") or StudyPlanService(deps)
        learn = overrides.get("learning") or LearningService(c_repo, LearningRepository(session), adapter)
        prefs = overrides.get("preferences") or PreferencesService(PreferencesRepository(session))
        qa = overrides.get("qa_notes") or QANotesService(c_repo, QANoteRepository(session), adapter, cfg)
        qa.web_search_fn = qa.web_search_fn or search_web_snippets
    return {
        "service": active_service,
        "study_service": active_study,
        "study_plan": plan,
        "learning": learn,
        "preferences": prefs,
        "qa_notes": qa,
        "fonts": overrides.get("fonts"),
    }


def _register_study_aid_tools(
    mcp: MCPServer, study_plan: StudyPlanService | None, learning: LearningService | None
) -> None:
    """Register the study-plan and learning-aid tools when those services exist.

    Args:
        mcp: MCPServer instance.
        study_plan: Study-plan service, or None.
        learning: Learning service, or None.
    """
    if study_plan is not None:
        register_study_plan_tools(mcp, study_plan)
    if learning is not None:
        register_learning_tools(mcp, learning)


def build_mcp_server(service: BatchStudioService | None = None, **services: Any) -> MCPServer:
    """Build and configure the MCPServer instance with all batch studio tools.

    Args:
        service: Optional pre-configured BatchStudioService instance.
        **services: Optional `study_service`, `config`, `study_plan`, `learning`, `preferences`, `fonts`.

    Returns:
        Configured MCPServer with registered tool handlers.
    """
    cfg: AppConfig = services.get("config") or load_config()
    resolved = _resolve_mcp_services(service, cfg, services)
    active_service: BatchStudioService = resolved["service"]
    active_study: StudyTrackerService = resolved["study_service"]

    mcp = MCPServer("notebooklm-batch-studio")
    _register_course_list_and_quota_tools(mcp, active_service)
    _register_course_status_tool(mcp, active_service)
    _register_quiz_read_tool(mcp, active_service)
    _register_artifact_list_tool(mcp, active_service)
    _register_import_tools(mcp, active_service)
    _register_queue_tools(mcp, active_service)
    _register_retry_tool(mcp, active_service)
    _register_sync_and_prompt_tools(mcp, active_service)
    register_settings_and_study_tools(mcp, active_service, active_study)
    register_course_settings_tools(mcp, active_service)
    register_job_prompt_tools(mcp, active_service)
    _register_study_aid_tools(mcp, resolved.get("study_plan"), resolved.get("learning"))
    if resolved.get("preferences") is not None:
        register_preferences_tools(mcp, resolved["preferences"])
    if resolved.get("qa_notes") is not None:
        register_qa_notes_tools(mcp, resolved["qa_notes"])
    register_remote_artifact_tools(mcp, active_service)
    register_font_tools(mcp, resolved.get("fonts") or FontService(cfg.fonts_dir, GoogleFontsClient()))
    register_literature_and_note_tools(mcp, cfg, resolved)
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

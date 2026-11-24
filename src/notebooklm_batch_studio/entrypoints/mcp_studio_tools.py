"""Study history, weaknesses, guide, and course settings MCP tools extracted from mcp_server."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.domain.naming import naming_guide
from notebooklm_batch_studio.domain.usage_guide import usage_guide
from notebooklm_batch_studio.entrypoints.mcp_confirm import confirm_warning
from notebooklm_batch_studio.services.folder_browser import browse_folders
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.study_service import StudyTrackerService


def _get_weaknesses_payload(
    active_study: StudyTrackerService, course_code: str, lecture_no: int | None, only_unresolved: bool
) -> str:
    """Serialize weakness mistake records as formatted JSON.

    Args:
        active_study: Study tracker service.
        course_code: Course identifier.
        lecture_no: Optional lecture number filter.
        only_unresolved: When True, return only unresolved mistakes.

    Returns:
        Formatted JSON string of weakness records.
    """
    mistakes = active_study.get_weaknesses(
        course_code, lecture_no=lecture_no, only_unresolved=only_unresolved
    )
    res = [
        {
            "id": m.id,
            "course_code": m.course_code,
            "lecture_no": m.lecture_no,
            "question_text": m.question_text,
            "choices": m.choices,
            "correct_index": m.correct_index,
            "selected_index": m.selected_index,
            "explanation": m.explanation,
            "is_resolved": m.is_resolved,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in mistakes
    ]
    return json.dumps(res, ensure_ascii=False, indent=2)


def _set_course_options_payload(
    active_service: BatchStudioService, code: str, options: dict[str, Any], confirm: bool
) -> str:
    """Validate confirmation and update course-level generation options.

    Args:
        active_service: Orchestrator service.
        code: Course code.
        options: Generation option updates.
        confirm: Explicit confirmation flag.

    Returns:
        JSON string response.
    """
    if not confirm:
        return json.dumps(
            {"confirmed": False, "warning": "Set confirm=True to save these options.", "options": options},
            ensure_ascii=False,
        )
    try:
        return json.dumps(active_service.course_settings.set_options(code, options), ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _regenerate_artifact_payload(
    active_service: BatchStudioService, code: str, artifact_type: str, target_opts: tuple[int | None, bool]
) -> str:
    """Validate confirmation and enqueue a regenerated artifact version.

    Args:
        active_service: Orchestrator service.
        code: Course code.
        artifact_type: Artifact type value string.
        target_opts: Tuple of `(lecture_no, confirm)`.

    Returns:
        JSON string response.
    """
    lecture_no, confirm = target_opts
    if not confirm:
        warning = "Set confirm=True to enqueue; this spends Gemini Notebook quota."
        return json.dumps({"confirmed": False, "warning": warning}, ensure_ascii=False)
    try:
        res = active_service.course_settings.regenerate(code, lecture_no, artifact_type)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    active_service.start_queue()
    return json.dumps(res, ensure_ascii=False)


def _set_artifact_types_payload(
    active_service: BatchStudioService, code: str, selection: tuple[list[str], list[str]], confirm: bool
) -> str:
    """Validate confirmation and update enabled artifact types for a course.

    Args:
        active_service: Orchestrator service.
        code: Course code.
        selection: Tuple of `(chapter_types, course_types)`.
        confirm: Explicit confirmation flag.

    Returns:
        JSON string response.
    """
    chapter, course = selection
    if not confirm:
        return json.dumps(
            {"confirmed": False, "warning": "Set confirm=True to apply; added types spend quota."},
            ensure_ascii=False,
        )
    try:
        result = active_service.course_settings.set_artifact_selection(code, chapter, course)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    if result.get("queued", 0) + result.get("revived", 0) > 0:
        active_service.start_queue()
    return json.dumps(result, ensure_ascii=False)


def _register_study_tools(mcp: MCPServer, active_study: StudyTrackerService) -> None:
    """Register student quiz history and weakness notebook tools.

    Args:
        mcp: MCPServer instance.
        active_study: Study tracker service.
    """
    _register_study_history_tool(mcp, active_study)
    _register_resolve_weakness_tool(mcp, active_study)
    _register_weakness_read_tool(mcp, active_study)


def _register_study_history_tool(mcp: MCPServer, active_study: StudyTrackerService) -> None:
    """Register the get_study_history MCP tool.

    Args:
        mcp: MCPServer instance.
        active_study: Study tracker service.
    """

    @mcp.tool()
    def get_study_history(course_code: str, lecture_no: int | None = None) -> str:
        """Retrieve student quiz attempt history for a course or specific lecture.

        Args:
            course_code: Course identifier (e.g. 'BIO101').
            lecture_no: Optional sequence number to filter attempts by lecture.

        Returns:
            JSON string containing list of quiz attempts and scores.
        """
        attempts = active_study.get_study_history(course_code, lecture_no=lecture_no)
        res = [
            {
                "id": a.id,
                "course_code": a.course_code,
                "lecture_no": a.lecture_no,
                "quiz_variant": a.quiz_variant,
                "score": a.score,
                "total_questions": a.total_questions,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in attempts
        ]
        return json.dumps(res, ensure_ascii=False, indent=2)


def _resolve_weakness_payload(active_study: StudyTrackerService, mistake_id: str, confirm: bool) -> str:
    """Resolve one weakness mistake record when confirmed.

    Args:
        active_study: Study tracker service.
        mistake_id: Mistake record UUID.
        confirm: Must be True to resolve the mistake.

    Returns:
        JSON confirmation warning or status message.
    """
    if not confirm:
        return confirm_warning(
            f"Action not confirmed. Pass confirm=True to mark mistake {mistake_id} as resolved."
        )
    if active_study.resolve_weakness(mistake_id):
        return f"Mistake {mistake_id} successfully marked as resolved."
    return f"Mistake {mistake_id} not found."


def _register_resolve_weakness_tool(mcp: MCPServer, active_study: StudyTrackerService) -> None:
    """Register the resolve_weakness_mistake MCP tool.

    Args:
        mcp: MCPServer instance.
        active_study: Study tracker service.
    """

    @mcp.tool()
    def resolve_weakness_mistake(mistake_id: str, confirm: bool = False) -> str:
        """Mark a weakness mistake question as resolved/mastered (requires confirm=True).

        Args:
            mistake_id: Mistake record UUID.
            confirm: Must be explicitly set to True to resolve the mistake.

        Returns:
            Status message.
        """
        return _resolve_weakness_payload(active_study, mistake_id, confirm)


def _register_weakness_read_tool(mcp: MCPServer, active_study: StudyTrackerService) -> None:
    """Register get_weaknesses tool.

    Args:
        mcp: MCPServer instance.
        active_study: Study tracker service.
    """

    @mcp.tool()
    def get_weaknesses(course_code: str, lecture_no: int | None = None, only_unresolved: bool = True) -> str:
        """Retrieve student mistake questions from the weakness notebook.

        Args:
            course_code: Course identifier (e.g. 'BIO101').
            lecture_no: Optional sequence number filter.
            only_unresolved: If True, only returns mistakes not yet mastered.

        Returns:
            JSON string containing wrong questions, answers, and academic rationales.
        """
        return _get_weaknesses_payload(active_study, course_code, lecture_no, only_unresolved)


def _register_guide_tools(mcp: MCPServer) -> None:
    """Register read-only naming and usage guide tools.

    Args:
        mcp: MCPServer instance.
    """

    @mcp.tool()
    def get_naming_guide() -> str:
        """Explain how artifacts are named on Gemini Notebook and locally (read-only).

        Returns:
            JSON string with naming rules and one row per artifact type.
        """
        return json.dumps(naming_guide(), ensure_ascii=False, indent=2)

    @mcp.tool()
    def get_usage_guide() -> str:
        """Explain how to use the studio and an effective study routine (read-only).

        Returns:
            JSON string with sections of headings and steps.
        """
        return json.dumps(usage_guide(), ensure_ascii=False, indent=2)


def _register_option_and_regen_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register course option read/write and versioned regeneration tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """
    _register_course_option_tools(mcp, active_service)
    _register_regenerate_tool(mcp, active_service)


def _register_course_option_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register get_course_options and set_course_options tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def get_course_options(code: str) -> str:
        """Read a course's Gemini Notebook generation options and allowed values (read-only).

        Args:
            code: Course code.

        Returns:
            JSON string with current options and choices.
        """
        try:
            return json.dumps(active_service.course_settings.get_options(code), ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def set_course_options(code: str, options: dict[str, Any], confirm: bool = False) -> str:
        """Change a course's generation options (requires confirm=True).

        Args:
            code: Course code.
            options: Option name to new value, e.g. {"infographic_orientation": "portrait"}.
            confirm: Must be True to save the change.

        Returns:
            JSON string with the updated options, or a confirmation warning.
        """
        return _set_course_options_payload(active_service, code, options, confirm)


def _register_regenerate_tool(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register regenerate_artifact tool.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def regenerate_artifact(
        code: str, artifact_type: str, lecture_no: int | None = None, confirm: bool = False
    ) -> str:
        """Enqueue a new version (v2, v3, ...) of one artifact; older versions are kept (requires confirm).

        Args:
            code: Course code.
            artifact_type: Artifact type value, e.g. 'infographic'.
            lecture_no: Lecture number, or None for a course-wide artifact.
            confirm: Must be True to enqueue (this spends Gemini Notebook quota).

        Returns:
            JSON string with the new job id and version, or a confirmation warning.
        """
        return _regenerate_artifact_payload(active_service, code, artifact_type, (lecture_no, confirm))


def _register_selection_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register folder browsing and course artifact selection tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """
    _register_folder_and_type_read_tools(mcp, active_service)
    _register_type_write_tool(mcp, active_service)


def _register_folder_and_type_read_tools(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register list_folders and get_course_artifact_types tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def list_folders(path: str = "") -> str:
        """List sub-folders and their PDF counts, to find course folders (read-only).

        Args:
            path: Absolute folder inside the home directory; empty for the starting shortcuts.

        Returns:
            JSON string with the folder, its parent and sub-folders.
        """
        try:
            data = browse_folders(path or None, active_service.config.courses_input_dir)
            return json.dumps(data, ensure_ascii=False, indent=2)
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    def get_course_artifact_types(code: str) -> str:
        """Read which artifact types a course generates (read-only).

        Args:
            code: Course code.

        Returns:
            JSON string with selected chapter / course types and the choices.
        """
        try:
            result = active_service.course_settings.get_artifact_selection(code)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_type_write_tool(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register set_course_artifact_types tool.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

    @mcp.tool()
    def set_course_artifact_types(
        code: str, chapter: list[str], course: list[str], confirm: bool = False
    ) -> str:
        """Change which artifact types a course generates (requires confirm=True).

        Args:
            code: Course code.
            chapter: Per-lecture artifact type values.
            course: Course-wide artifact type values.
            confirm: Must be True to apply.

        Returns:
            JSON string with queued / revived / skipped counts, or a confirmation warning.
        """
        return _set_artifact_types_payload(active_service, code, (chapter, course), confirm)


def _set_course_profile_payload(
    active_service: BatchStudioService, course_code: str, profile: str, confirm: bool
) -> str:
    """Update a course's active profile when confirmed.

    Args:
        active_service: Orchestrator service.
        course_code: Course code identifier.
        profile: Target profile name.
        confirm: Must be True to commit the update.

    Returns:
        Result JSON or confirmation warning.
    """
    if not confirm:
        return confirm_warning(
            f"Action not confirmed. Pass confirm=True to update course {course_code} profile to '{profile}'."
        )
    try:
        payload = active_service.set_course_profile(course_code, profile)
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_course_profile_tool(mcp: MCPServer, active_service: BatchStudioService) -> None:
    """Register the set_course_profile MCP tool.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
    """

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
        return _set_course_profile_payload(active_service, course_code, profile, confirm)


def register_settings_and_study_tools(
    mcp: MCPServer, active_service: BatchStudioService, active_study: StudyTrackerService
) -> None:
    """Register study tracking, guide, option, regeneration, and selection MCP tools.

    Args:
        mcp: MCPServer instance.
        active_service: Orchestrator service.
        active_study: Study tracker service.
    """
    _register_study_tools(mcp, active_study)
    _register_guide_tools(mcp)
    _register_option_and_regen_tools(mcp, active_service)
    _register_selection_tools(mcp, active_service)
    _register_course_profile_tool(mcp, active_service)

"""MCP tools for the student's study plan, progress, spaced review and explanations."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.services.study_plan_service import StudyPlanService


def _mark_step_payload(
    plan: StudyPlanService, code: str, step: str, options_and_confirm: tuple[dict[str, Any] | None, bool]
) -> str:
    """Validate confirmation and mark or unmark a study step on the study plan.

    Args:
        plan: Study plan service.
        code: Course code.
        step: Step key ('audio' or 'guide').
        options_and_confirm: Tuple of `(optional_dict_with_lecture_no_and_done, confirm_bool)`.

    Returns:
        JSON string response.
    """
    opts, confirm = options_and_confirm
    if not confirm:
        return json.dumps({"confirmed": False, "warning": "Set confirm=True to save."}, ensure_ascii=False)
    opts = opts or {}
    lecture_no = opts.get("lecture_no")
    done = bool(opts.get("done", True))
    try:
        return json.dumps(plan.mark_step(code, lecture_no, step, done), ensure_ascii=False, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


async def _explain_question_payload(
    plan: StudyPlanService, code: str, question: str, details_and_confirm: tuple[dict[str, Any], bool]
) -> str:
    """Validate confirmation and ask Gemini Notebook for a grounded answer explanation.

    Args:
        plan: Study plan service.
        code: Course code.
        question: Question stem text.
        details_and_confirm: Tuple of `(details_dict, confirm_bool)`.

    Returns:
        JSON string response.
    """
    details, confirm = details_and_confirm
    if not confirm:
        warning = "Set confirm=True; this asks Gemini Notebook and uses a little quota."
        return json.dumps({"confirmed": False, "warning": warning}, ensure_ascii=False)
    try:
        result = await plan.explain(
            code,
            details.get("lecture_no"),
            question,
            choices=details["choices"],
            answer_index=details["answer_index"],
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_plan_overview_tool(mcp: MCPServer, plan: StudyPlanService) -> None:
    """Register the read-only study plan overview MCP tool.

    Args:
        mcp: MCPServer instance.
        plan: Study plan service.
    """

    @mcp.tool()
    def get_study_plan(code: str) -> str:
        """Today's plan: next step, per-lecture progress, exam countdown, reviews due (read-only).

        Args:
            code: Course code.

        Returns:
            JSON string with the plan.
        """
        try:
            return json.dumps(plan.get_plan(code), ensure_ascii=False, indent=2, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _register_review_read_tools(mcp: MCPServer, plan: StudyPlanService) -> None:
    """Register read-only due reviews and saved explanations MCP tools.

    Args:
        mcp: MCPServer instance.
        plan: Study plan service.
    """

    @mcp.tool()
    def get_due_reviews(code: str, lecture_no: int | None = None) -> str:
        """Flashcards and mistakes due for review now (read-only).

        Args:
            code: Course code.
            lecture_no: Optional lecture filter.

        Returns:
            JSON string with due items.
        """
        return json.dumps(plan.due_reviews(code, lecture_no), ensure_ascii=False, indent=2)

    @mcp.tool()
    def get_saved_explanations(code: str, lecture_no: int | None = None) -> str:
        """Saved Gemini Notebook explanations of quiz questions (read-only, no quota).

        Args:
            code: Course code.
            lecture_no: Optional lecture filter.

        Returns:
            JSON string with saved explanations (Markdown).
        """
        items = [
            {k: v for k, v in i.items() if k != "html"} for i in plan.list_explanations(code, lecture_no)
        ]
        return json.dumps(items, ensure_ascii=False, indent=2, default=str)


def _register_mark_step_tool(mcp: MCPServer, plan: StudyPlanService) -> None:
    """Register the mark_study_step write tool.

    Args:
        mcp: MCPServer instance.
        plan: Study plan service.
    """

    @mcp.tool()
    def mark_study_step(
        code: str, step: str, options: dict[str, Any] | None = None, confirm: bool = False
    ) -> str:
        """Mark 'audio' or 'guide' done or undone for a lecture (requires confirm=True).

        Args:
            code: Course code.
            step: 'audio' or 'guide'.
            options: Optional dict with `lecture_no` (int) and `done` (bool, default True).
            confirm: Must be True to save.

        Returns:
            JSON string with the updated plan, or a confirmation warning.
        """
        return _mark_step_payload(plan, code, step, (options, confirm))


def _register_explain_tool(mcp: MCPServer, plan: StudyPlanService) -> None:
    """Register the explain_question write tool.

    Args:
        mcp: MCPServer instance.
        plan: Study plan service.
    """

    @mcp.tool()
    async def explain_question(
        code: str, question: str, details: dict[str, Any], confirm: bool = False
    ) -> str:
        """Ask Gemini Notebook why an answer is correct, from the course's sources (requires confirm=True).

        Args:
            code: Course code.
            question: Question text.
            details: Dict with `choices` (list[str]), `answer_index` (int), and optional `lecture_no`.
            confirm: Must be True (this uses a little Gemini Notebook quota).

        Returns:
            JSON string with the explanation, or a confirmation warning.
        """
        return await _explain_question_payload(plan, code, question, (details, confirm))


def register_study_plan_tools(mcp: MCPServer, plan: StudyPlanService) -> None:
    """Register study-plan tools (changes and Gemini Notebook calls require confirm=True).

    Args:
        mcp: MCPServer instance.
        plan: Study plan service.
    """
    _register_plan_overview_tool(mcp, plan)
    _register_review_read_tools(mcp, plan)
    _register_mark_step_tool(mcp, plan)
    _register_explain_tool(mcp, plan)

"""MCP tools for the student's study plan, progress, spaced review and explanations."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from notebooklm_batch_studio.services.study_plan_service import StudyPlanService


def register_study_plan_tools(mcp: MCPServer, plan: StudyPlanService) -> None:
    """Register study-plan tools (changes and NotebookLM calls require confirm=True).

    Args:
        mcp: MCPServer instance.
        plan: Study plan service.
    """
    _register_read_tools(mcp, plan)
    _register_write_tools(mcp, plan)


def _register_read_tools(mcp: MCPServer, plan: StudyPlanService) -> None:
    """Register the read-only study-plan tools.

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
        """Saved NotebookLM explanations of quiz questions (read-only, no quota).

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


def _register_write_tools(mcp: MCPServer, plan: StudyPlanService) -> None:
    """Register study-plan tools that save data or call NotebookLM (confirm required).

    Args:
        mcp: MCPServer instance.
        plan: Study plan service.
    """

    @mcp.tool()
    def mark_study_step(
        code: str, step: str, lecture_no: int | None = None, done: bool = True, confirm: bool = False
    ) -> str:
        """Mark 'audio' or 'guide' done for a lecture (requires confirm=True).

        Args:
            code: Course code.
            step: 'audio' or 'guide'.
            lecture_no: Lecture number.
            done: True to mark done, False to undo.
            confirm: Must be True to save.

        Returns:
            JSON string with the updated plan, or a confirmation warning.
        """
        if not confirm:
            return json.dumps(
                {"confirmed": False, "warning": "Set confirm=True to save."}, ensure_ascii=False
            )
        try:
            return json.dumps(plan.mark_step(code, lecture_no, step, done), ensure_ascii=False, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @mcp.tool()
    async def explain_question(
        code: str,
        question: str,
        choices: list[str],
        answer_index: int,
        lecture_no: int | None = None,
        confirm: bool = False,
    ) -> str:
        """Ask NotebookLM why an answer is correct, from the course's sources (requires confirm=True).

        Args:
            code: Course code.
            question: Question text.
            choices: Options in display order.
            answer_index: Index of the correct option.
            lecture_no: Lecture number, or None for course-wide.
            confirm: Must be True (this uses a little NotebookLM quota).

        Returns:
            JSON string with the explanation, or a confirmation warning.
        """
        if not confirm:
            return json.dumps(
                {
                    "confirmed": False,
                    "warning": "Set confirm=True; this asks NotebookLM and uses a little quota.",
                },
                ensure_ascii=False,
            )
        try:
            result = await plan.explain(code, lecture_no, question, choices, answer_index)
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

"""Remote artifact admin mixin for NotebookLMAdapter (cinematic video, slide, export)."""

from __future__ import annotations

from typing import Any

from notebooklm import ChatGoal, ChatResponseLength

from notebooklm_batch_studio.adapters.notebooklm.errors import _translate_errors
from notebooklm_batch_studio.adapters.notebooklm.generation import finish_generation, to_nlm_language


class NotebookLMRemoteAdminMixin:
    """Mixin adding advanced remote artifact operations to NotebookLMAdapter."""

    _client: Any

    @_translate_errors
    async def generate_cinematic_video(
        self,
        notebook_id: str,
        instructions: str,
        source_ids: list[str] | None = None,
        language: str = "zh-TW",
    ) -> str:
        """Generate a cinematic video overview and wait for completion.

        Args:
            notebook_id: Notebook identifier.
            instructions: Focus prompt instructions.
            source_ids: Optional source IDs to scope generation.
            language: Output language code.

        Returns:
            Generated artifact identifier.
        """
        async with self._client() as client:
            status = await client.artifacts.generate_cinematic_video(
                notebook_id,
                source_ids=source_ids,
                language=to_nlm_language(language),
                instructions=instructions,
            )
            return str(
                await finish_generation(client, notebook_id, status, label="cinematic_video", timeout=1800.0)
            )

    @_translate_errors
    async def revise_slide(self, notebook_id: str, artifact_id: str, slide_index: int, prompt: str) -> str:
        """Revise a single slide in an existing slide deck artifact.

        Args:
            notebook_id: Notebook identifier.
            artifact_id: Slide deck artifact identifier.
            slide_index: Zero-based slide index.
            prompt: Revision instructions.

        Returns:
            Updated artifact identifier.
        """
        async with self._client() as client:
            status = await client.artifacts.revise_slide(notebook_id, artifact_id, slide_index, prompt)
            return str(
                await finish_generation(client, notebook_id, status, label="slide_deck", timeout=600.0)
            )

    @_translate_errors
    async def export_artifact(
        self, notebook_id: str, artifact_id: str, title: str = "Export", kind: str = "report"
    ) -> dict[str, Any]:
        """Export a remote report or data table to Google Docs or Google Sheets.

        Args:
            notebook_id: Notebook identifier.
            artifact_id: Remote artifact identifier.
            title: Exported document title.
            kind: Artifact kind ('report' or 'data_table').

        Returns:
            Export result dictionary.
        """
        async with self._client() as client:
            if kind == "data_table":
                res = await client.artifacts.export_data_table(notebook_id, artifact_id, title=title)
            else:
                res = await client.artifacts.export_report(notebook_id, artifact_id, title=title)
        return {"artifact_id": artifact_id, "title": title, "kind": kind, "result": str(res)}

    @_translate_errors
    async def suggest_reports(self, notebook_id: str) -> list[dict[str, Any]]:
        """List AI-suggested report topics for a notebook.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            List of suggestion dictionaries.
        """
        async with self._client() as client:
            items = await client.artifacts.suggest_reports(notebook_id)
        return [
            {
                "title": str(getattr(s, "title", "") or ""),
                "description": str(getattr(s, "description", "") or ""),
                "prompt": str(getattr(s, "prompt", "") or ""),
                "audience_level": str(getattr(s, "audience_level", "") or ""),
            }
            for s in (items or [])
        ]

    @_translate_errors
    async def retry_remote_artifact(self, notebook_id: str, artifact_id: str) -> dict[str, Any]:
        """Retry a failed remote artifact generation directly on Gemini Notebook.

        Args:
            notebook_id: Notebook identifier.
            artifact_id: Failed artifact identifier.

        Returns:
            Retry status dictionary.
        """
        async with self._client() as client:
            status = await client.artifacts.retry_failed(notebook_id, artifact_id)
        return {
            "artifact_id": getattr(status, "artifact_id", artifact_id) or artifact_id,
            "task_id": getattr(status, "task_id", None),
            "status": str(getattr(status, "status", "submitted")),
        }

    @_translate_errors
    async def add_url_source(self, notebook_id: str, url: str, title: str | None = None) -> dict[str, Any]:
        """Add a web page or YouTube URL as a source in Gemini Notebook.

        Args:
            notebook_id: Notebook identifier.
            url: Target web or YouTube URL.
            title: Optional source title override.

        Returns:
            Created source summary dictionary.
        """
        async with self._client() as client:
            src = await client.sources.add_url(notebook_id, url, wait=True, title=title)
        return {"id": str(getattr(src, "id", "") or ""), "title": str(getattr(src, "title", "") or url)}

    @_translate_errors
    async def add_text_source(self, notebook_id: str, title: str, content: str) -> dict[str, Any]:
        """Add pasted plain text as a source in Gemini Notebook.

        Args:
            notebook_id: Notebook identifier.
            title: Source title.
            content: Plain text body.

        Returns:
            Created source summary dictionary.
        """
        async with self._client() as client:
            src = await client.sources.add_text(notebook_id, title, content, wait=True)
        return {"id": str(getattr(src, "id", "") or ""), "title": str(getattr(src, "title", "") or title)}

    @_translate_errors
    async def research_sources(self, notebook_id: str, query: str, mode: str = "fast") -> dict[str, Any]:
        """Run web discovery research in a notebook and return candidate sources.

        Args:
            notebook_id: Notebook identifier.
            query: Search topic or research question.
            mode: Discovery mode ('fast' or 'deep').

        Returns:
            Research task dictionary with task_id, summary, and discovered sources.
        """
        async with self._client() as client:
            task = await client.research.discover(notebook_id, query, mode=mode)
        sources = [
            {
                "url": str(getattr(s, "url", "") or ""),
                "title": str(getattr(s, "title", "") or ""),
                "snippet": str(getattr(s, "snippet", "") or ""),
            }
            for s in (getattr(task, "sources", None) or [])
        ]
        return {
            "task_id": str(getattr(task, "task_id", "") or ""),
            "summary": str(getattr(task, "summary", "") or ""),
            "sources": sources,
        }

    @_translate_errors
    async def import_research_sources(
        self, notebook_id: str, task_id: str, sources: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Import selected discovered research sources into a notebook.

        Args:
            notebook_id: Notebook identifier.
            task_id: Research task identifier.
            sources: List of source dicts (`url`, `title`).

        Returns:
            List of imported source records.
        """
        async with self._client() as client:
            return list(await client.research.import_sources(notebook_id, task_id, sources))

    @_translate_errors
    async def configure_chat(
        self,
        notebook_id: str,
        goal: str = "default",
        response_length: str = "default",
        custom_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Configure chat goal and response length for a notebook.

        Args:
            notebook_id: Notebook identifier.
            goal: Chat goal ('default', 'learning_guide', 'custom').
            response_length: Response length ('default', 'shorter', 'longer').
            custom_prompt: Custom instructions when goal is 'custom'.

        Returns:
            Applied configuration dictionary.
        """
        goal_map = {
            "default": ChatGoal.DEFAULT,
            "learning_guide": ChatGoal.LEARNING_GUIDE,
            "custom": ChatGoal.CUSTOM,
        }
        len_map = {
            "default": ChatResponseLength.DEFAULT,
            "shorter": ChatResponseLength.SHORTER,
            "longer": ChatResponseLength.LONGER,
        }
        async with self._client() as client:
            await client.chat.configure(
                notebook_id,
                goal=goal_map.get(goal, ChatGoal.DEFAULT),
                response_length=len_map.get(response_length, ChatResponseLength.DEFAULT),
                custom_prompt=custom_prompt,
            )
        return {"goal": goal, "response_length": response_length, "custom_prompt": custom_prompt}

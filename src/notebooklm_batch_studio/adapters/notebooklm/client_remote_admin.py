"""Remote artifact admin mixin for NotebookLMAdapter (cinematic video, slide, export)."""

from __future__ import annotations

from typing import Any

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

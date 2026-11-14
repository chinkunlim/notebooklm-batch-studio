"""Artifact generation, listing, renaming, and download helpers for NotebookLMAdapter."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from notebooklm import ReportFormat
from notebooklm.types import MindMapKind

from notebooklm_batch_studio.adapters.notebooklm.errors import (
    CONCEPT_EXPLANATION_DIRECTIVE,
    _translate_errors,
    build_language_instruction,
)
from notebooklm_batch_studio.adapters.notebooklm.generation import (
    finish_generation,
    generation_kwargs,
    to_nlm_language,
    to_quiz_difficulty,
)
from notebooklm_batch_studio.domain.exceptions import IncompleteArtifactError

logger = logging.getLogger(__name__)

_DOWNLOAD_METHOD_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("quiz", "exam"), "download_quiz"),
    (("flashcard",), "download_flashcards"),
    (("audio",), "download_audio"),
    (("report", "briefing", "study_guide"), "download_report"),
    (("slide",), "download_slide_deck"),
    (("infographic",), "download_infographic"),
    (("mind_map", "mindmap"), "download_mind_map"),
    (("data_table", "table"), "download_data_table"),
    (("video",), "download_video"),
)


def _report_format_and_kwargs(report_format: str, instructions: str) -> tuple[ReportFormat, dict[str, Any]]:
    """Build notebooklm-py ReportFormat and instruction kwargs for a report type.

    Args:
        report_format: Logical report format key.
        instructions: Language-prefixed instructions string.

    Returns:
        Tuple of (`ReportFormat`, kwargs dict).
    """
    formats = {"study_guide": ReportFormat.STUDY_GUIDE, "blog_post": ReportFormat.BLOG_POST}
    if report_format == "concept_explanation":
        return ReportFormat.CUSTOM, {"custom_prompt": f"{CONCEPT_EXPLANATION_DIRECTIVE}\n\n{instructions}"}
    return formats.get(report_format, ReportFormat.BRIEFING_DOC), {"extra_instructions": instructions}


def _serialize_artifact(artifact: Any) -> dict[str, Any]:
    """Convert one remote notebooklm-py artifact object into a summary dict.

    Args:
        artifact: Remote artifact descriptor returned by `client.artifacts.list`.

    Returns:
        Normalized metadata dictionary.
    """
    kind_str = artifact.kind.value if hasattr(artifact.kind, "value") else str(artifact.kind)
    return {
        "id": str(artifact.id),
        "title": getattr(artifact, "title", None) or "Untitled",
        "kind": kind_str.lower(),
        "status": getattr(artifact, "status_str", "done"),
        "is_completed": getattr(artifact, "is_completed", True),
        "created_at": str(getattr(artifact, "created_at", "")),
    }


def _downloader_name_for_kind(kind: str) -> str:
    """Resolve the `client.artifacts.download_*` method name for an artifact kind string.

    Args:
        kind: Artifact type or label string.

    Returns:
        Attribute name on `client.artifacts`.
    """
    k = kind.lower()
    for needles, method_name in _DOWNLOAD_METHOD_RULES:
        if any(needle in k for needle in needles):
            return method_name
    return "download_report"


class ArtifactOperationsMixin:
    """Artifact studio generation, listing, rename, and download methods for NotebookLMAdapter."""

    def _client(self) -> Any:
        """Open a notebooklm-py client context; implemented by concrete adapter.

        Returns:
            Async context manager yielding a client.
        """
        raise NotImplementedError

    @_translate_errors
    async def generate_quiz(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, **kwargs: Any
    ) -> str:
        """Generate a quiz from selected sources and wait for it to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for the quiz generation.
            **kwargs: Optional `difficulty` ('easy'/'medium'/'hard') and `options` (`GenerationOptions`).

        Returns:
            The completed quiz artifact id.
        """
        difficulty = kwargs.get("difficulty")
        options = kwargs.get("options")
        instructions = prompt or "Generate multiple choice questions with 4 options and detailed rationale."
        async with self._client() as client:
            status = await client.artifacts.generate_quiz(
                notebook_id=notebook_id,
                source_ids=source_ids,
                instructions=instructions,
                difficulty=to_quiz_difficulty(difficulty),
                **generation_kwargs("quiz", options),
            )
            return await finish_generation(client, notebook_id, status, label="quiz")

    @_translate_errors
    async def generate_flashcards(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        options: Any = None,
    ) -> str:
        """Generate flashcards from selected sources and wait for them to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for flashcards generation.
            options: Course generation options (None = defaults).

        Returns:
            The completed flashcards artifact id.
        """
        instructions = prompt or "Extract key vocabulary, core concepts, and biochemical mechanisms."
        async with self._client() as client:
            status = await client.artifacts.generate_flashcards(
                notebook_id=notebook_id,
                source_ids=source_ids,
                instructions=instructions,
                **generation_kwargs("flashcards", options),
            )
            return await finish_generation(client, notebook_id, status, label="flashcards")

    @_translate_errors
    async def generate_mind_map(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Generate a note-backed mind map (synchronous in Gemini Notebook).

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for mind map generation.
            language: Course language ('zh-TW', 'en', 'bilingual').

        Returns:
            The id of the note the mind map was saved to.

        Raises:
            IncompleteArtifactError: When Gemini Notebook returned no mind map note.
        """
        instructions = prompt or "Create a detailed hierarchical mind map organizing concepts."
        async with self._client() as client:
            result = await client.artifacts.generate_mind_map(
                notebook_id=notebook_id,
                source_ids=source_ids,
                language=to_nlm_language(language),
                instructions=instructions,
            )
        if not result.note_id:
            raise IncompleteArtifactError("Gemini Notebook returned no mind map note")
        logger.info("Mind map saved as note %s", result.note_id)
        return str(result.note_id)

    @_translate_errors
    async def generate_audio(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, **kwargs: Any
    ) -> str:
        """Generate a Deep Dive audio overview and wait for it to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional customization prompt for audio discussion.
            **kwargs: Optional `language` ('zh-TW'/'en'/'bilingual') and `options` (`GenerationOptions`).

        Returns:
            The completed audio artifact id.
        """
        language = str(kwargs.get("language", "zh-TW"))
        options = kwargs.get("options")
        instructions = prompt or "Discuss key points, mechanisms, and exam takeaways."
        async with self._client() as client:
            status = await client.artifacts.generate_audio(
                notebook_id=notebook_id,
                source_ids=source_ids,
                language=to_nlm_language(language),
                instructions=instructions,
                **generation_kwargs("audio", options),
            )
            return await finish_generation(client, notebook_id, status, label="audio")

    @_translate_errors
    async def generate_report(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, **kwargs: Any
    ) -> str:
        """Generate a report (briefing doc, study guide, blog post, or concept explanation).

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            **kwargs: Optional `language` ('zh-TW'/'en'/'bilingual') and `report_format`.

        Returns:
            The completed report artifact id.
        """
        language = str(kwargs.get("language", "zh-TW"))
        report_format = str(kwargs.get("report_format", "briefing_doc"))
        instructions = build_language_instruction(prompt, language)
        fmt, fmt_kwargs = _report_format_and_kwargs(report_format, instructions)
        async with self._client() as client:
            status = await client.artifacts.generate_report(
                notebook_id=notebook_id,
                report_format=fmt,
                source_ids=source_ids,
                language=to_nlm_language(language),
                **fmt_kwargs,
            )
            return await finish_generation(client, notebook_id, status, label=f"report ({report_format})")

    @_translate_errors
    async def generate_slide_deck(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, **kwargs: Any
    ) -> str:
        """Generate a slide deck and wait for it to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            **kwargs: Optional `language` and `options` (`GenerationOptions`).

        Returns:
            The completed slide deck artifact id.
        """
        language = str(kwargs.get("language", "zh-TW"))
        options = kwargs.get("options")
        async with self._client() as client:
            status = await client.artifacts.generate_slide_deck(
                notebook_id=notebook_id,
                source_ids=source_ids,
                language=to_nlm_language(language),
                instructions=build_language_instruction(prompt, language),
                **generation_kwargs("slide_deck", options),
            )
            return await finish_generation(client, notebook_id, status, label="slide deck")

    @_translate_errors
    async def generate_infographic(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, **kwargs: Any
    ) -> str:
        """Generate an infographic and wait for it to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            **kwargs: Optional `language` and `options` (`GenerationOptions`).

        Returns:
            The completed infographic artifact id.
        """
        language = str(kwargs.get("language", "zh-TW"))
        options = kwargs.get("options")
        async with self._client() as client:
            status = await client.artifacts.generate_infographic(
                notebook_id=notebook_id,
                source_ids=source_ids,
                language=to_nlm_language(language),
                instructions=build_language_instruction(prompt, language),
                **generation_kwargs("infographic", options),
            )
            return await finish_generation(client, notebook_id, status, label="infographic")

    @_translate_errors
    async def generate_data_table(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Generate a comparison data table and wait for it to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Course language ('zh-TW', 'en', 'bilingual').

        Returns:
            The completed data table artifact id.
        """
        async with self._client() as client:
            status = await client.artifacts.generate_data_table(
                notebook_id=notebook_id,
                source_ids=source_ids,
                language=to_nlm_language(language),
                instructions=build_language_instruction(prompt, language),
            )
            return await finish_generation(client, notebook_id, status, label="data table")

    @_translate_errors
    async def generate_video(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, **kwargs: Any
    ) -> str:
        """Generate a video overview and wait for it to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            **kwargs: Optional `language` and `options` (`GenerationOptions`).

        Returns:
            The completed video artifact id.
        """
        language = str(kwargs.get("language", "zh-TW"))
        options = kwargs.get("options")
        async with self._client() as client:
            status = await client.artifacts.generate_video(
                notebook_id=notebook_id,
                source_ids=source_ids,
                language=to_nlm_language(language),
                instructions=build_language_instruction(prompt, language),
                **generation_kwargs("video", options),
            )
            return await finish_generation(client, notebook_id, status, label="video", timeout=1800.0)

    @_translate_errors
    async def download_artifact(self, kind: str, notebook_id: str, output_path: str, **extra: Any) -> None:
        """Download one specific artifact with the notebooklm-py downloader for its kind.

        Args:
            kind: Downloader suffix (quiz, flashcards, mind_map, audio, report, slide_deck,
                infographic, data_table, video).
            notebook_id: The notebook identifier.
            output_path: Local filesystem destination.
            **extra: Must include `artifact_id` plus any downloader keywords (e.g. `output_format`).
        """
        artifact_id = str(extra.pop("artifact_id", ""))
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with self._client() as client:
            logger.info("Downloading %s %s from notebook %s to %s", kind, artifact_id, notebook_id, out)
            downloader = getattr(client.artifacts, f"download_{kind}")
            await downloader(notebook_id, str(out), artifact_id=artifact_id, **extra)

    @_translate_errors
    async def rename_artifact(self, notebook_id: str, artifact_id: str, title: str) -> None:
        """Rename an artifact within Gemini Notebook for readability.

        Args:
            notebook_id: The notebook identifier.
            artifact_id: The artifact identifier to rename.
            title: The new title string (e.g. '[03] Quiz 1-基礎').
        """
        async with self._client() as client:
            logger.info("Renaming artifact %s to '%s' in notebook %s", artifact_id, title, notebook_id)
            try:
                await client.artifacts.rename(notebook_id, artifact_id, title)
            except Exception as err:
                logger.warning("Could not rename artifact %s on Gemini Notebook: %s", artifact_id, err)

    @_translate_errors
    async def rename_mind_map(self, notebook_id: str, note_id: str, title: str) -> None:
        """Rename a note-backed mind map within Gemini Notebook. Refs: ISSUE-011

        Args:
            notebook_id: The notebook identifier.
            note_id: The mind map note identifier.
            title: The new title string.
        """
        async with self._client() as client:
            logger.info("Renaming mind map %s to '%s' in notebook %s", note_id, title, notebook_id)
            await client.mind_maps.rename(
                notebook_id, note_id, title, kind=MindMapKind.NOTE_BACKED, return_object=False
            )

    @_translate_errors
    async def list_artifacts(self, notebook_id: str) -> list[dict[str, Any]]:
        """List all remote artifacts present in a notebook.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            List of dictionary summaries of artifacts.
        """
        async with self._client() as client:
            artifacts = await client.artifacts.list(notebook_id)
        return [_serialize_artifact(artifact) for artifact in artifacts]

    @_translate_errors
    async def delete_artifact(self, notebook_id: str, artifact_id: str) -> None:
        """Delete a remote artifact from Gemini Notebook.

        Args:
            notebook_id: Notebook identifier.
            artifact_id: Remote artifact identifier.
        """
        async with self._client() as client:
            logger.info("Deleting remote artifact %s in notebook %s", artifact_id, notebook_id)
            await client.artifacts.delete(notebook_id, artifact_id)

    @_translate_errors
    async def download_artifact_by_kind(
        self, notebook_id: str, artifact_id: str, kind: str, output_path: str
    ) -> str:
        """Download remote artifact using the method matching its kind.

        Args:
            notebook_id: Notebook identifier.
            artifact_id: Artifact identifier.
            kind: Artifact kind string.
            output_path: Target path.

        Returns:
            Target output path string.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        method_name = _downloader_name_for_kind(kind)
        async with self._client() as client:
            await getattr(client.artifacts, method_name)(notebook_id, str(out), artifact_id=artifact_id)
        return str(out)

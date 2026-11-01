"""NotebookLM API adapter: encapsulates NotebookLM client and maps exceptions to domain errors.

Provides resilient operations for uploading course PDFs, generating quizzes,
flashcards, mind maps, audio overviews, and downloading raw artifacts with
error translation for quota limits and authentication expiration.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, TypeVar

from notebooklm import (
    ArtifactError,
    ArtifactParseError,
    ArtifactTimeoutError,
    AuthError,
    NotebookLMClient,
    RateLimitError,
    ReportFormat,
)
from notebooklm.types import MindMapKind

from notebooklm_batch_studio.adapters.notebooklm.generation import (
    finish_generation,
    generation_kwargs,
    to_nlm_language,
    to_quiz_difficulty,
)
from notebooklm_batch_studio.adapters.notebooklm.quota import retry_after_from_usage, usage_to_dict
from notebooklm_batch_studio.config.settings import AppConfig, load_config
from notebooklm_batch_studio.domain.exceptions import (
    AuthExpiredError,
    IncompleteArtifactError,
    QuotaExceededError,
    StudioError,
)
from notebooklm_batch_studio.domain.models import GenerationOptions

logger = logging.getLogger(__name__)

T = TypeVar("T")


def build_language_instruction(base_prompt: str | None, language: str = "zh-TW") -> str:
    """Combine base prompt instructions with explicit language directives.

    Args:
        base_prompt: Optional base instructional prompt.
        language: Language code ('zh-TW', 'en', 'bilingual').

    Returns:
        Complete instructions string.
    """
    if language == "en":
        prefix = "Please generate all output strictly in English."
    elif language == "bilingual":
        prefix = (
            "Generate bilingual output in both English and Traditional Chinese. "
            "For all titles, questions, choices, key concepts, explanations, and flashcards, "
            "provide both English and Traditional Chinese (e.g. 'Concept / 概念')."
        )
    else:  # default zh-TW
        prefix = "請以繁體中文生成內容，專業學術名詞保留英文原名。"

    if base_prompt:
        return f"{prefix} {base_prompt}"
    return prefix


def _map_exception(err: Exception) -> Exception:
    """Map external provider errors into domain-specific exceptions.

    Args:
        err: Caught exception from NotebookLM client or network call.

    Returns:
        Mapped domain exception.
    """
    if isinstance(err, StudioError):
        return err
    if isinstance(err, RateLimitError):
        logger.warning("NotebookLM Rate Limit exceeded: %s", err)
        return QuotaExceededError(
            message=f"NotebookLM API quota or rate limit reached: {err}",
            retry_after_seconds=3600,
        )
    if isinstance(err, AuthError):
        logger.error("NotebookLM Authentication error: %s", err)
        return AuthExpiredError(f"NotebookLM credentials invalid or expired: {err}")
    if isinstance(err, FileNotFoundError) and "storage_state.json" in str(err):
        return AuthExpiredError("Authentication storage file not found. Please log in first.")
    if isinstance(err, (ArtifactTimeoutError, ArtifactParseError)):
        return IncompleteArtifactError(f"Artifact generation incomplete: {err}")
    if isinstance(err, ArtifactError):
        msg = str(err).lower()
        if "quota" in msg or "rate limit" in msg or "resource_exhausted" in msg:
            return QuotaExceededError(message=f"NotebookLM quota limit encountered: {err}")
        return StudioError(f"NotebookLM artifact operation failed: {err}")

    err_msg = str(err).lower()
    if "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
        return QuotaExceededError(message=f"NotebookLM rate limit hit: {err}")
    if "401" in err_msg or "403" in err_msg or "unauthorized" in err_msg:
        return AuthExpiredError(f"NotebookLM authorization failed: {err}")
    return err


def _translate_errors(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
    """Decorator to catch provider-specific exceptions and raise domain-specific errors.

    Args:
        func: The asynchronous adapter method to wrap.

    Returns:
        The wrapped asynchronous method.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        """Execute wrapped coroutine and translate any raised provider exceptions.

        Args:
            *args: Positional arguments for the wrapped method.
            **kwargs: Keyword arguments for the wrapped method.

        Returns:
            The return value of the wrapped coroutine.
        """
        try:
            return await func(*args, **kwargs)
        except Exception as err:
            mapped = _map_exception(err)
            if isinstance(mapped, QuotaExceededError) and args and isinstance(args[0], NotebookLMAdapter):
                retry_after = await args[0].quota_retry_after()
                if retry_after is not None:
                    mapped.retry_after_seconds = retry_after
            if mapped is not err:
                raise mapped from err
            if isinstance(err, StudioError):
                raise
            logger.exception("Unexpected error communicating with NotebookLM: %s", err)
            raise

    return wrapper


class NotebookLMAdapter:
    """Adapter implementing NotebookLMClientProtocol using official notebooklm-py client.

    Every `generate_*` passes the course output language, checks the returned status, waits for
    completion, and returns the artifact id; downloads take that id so parallel workers never
    fetch another lecture's artifact. Refs: ADR-004
    """

    def __init__(
        self,
        config: AppConfig | None = None,
        storage_path: Path | None = None,
    ) -> None:
        """Initialize the NotebookLM adapter.

        Args:
            config: Application configuration (defaults to global settings).
            storage_path: Custom path to Playwright storage_state.json file.
        """
        self.config = config or load_config()
        self.storage_path = storage_path or (
            self.config.notebooklm_home / "profiles" / "default" / "storage_state.json"
        )

    def _client(self) -> Any:
        """Open a notebooklm-py client from the stored browser session.

        Returns:
            Async context manager yielding a `NotebookLMClient`.
        """
        return NotebookLMClient.from_storage(path=str(self.storage_path))

    def check_auth(self) -> bool:
        """Check whether local authentication credentials exist and are non-empty.

        Returns:
            True if credentials file exists and has content, False otherwise.
        """
        if self.storage_path.exists() and self.storage_path.stat().st_size > 0:
            return True
        return False

    async def quota_retry_after(self) -> int | None:
        """Read the live usage meter and compute seconds until quota resets.

        Returns:
            Seconds until the exhausted window resets, or None if unknown (never raises).
        """
        try:
            async with self._client() as client:
                usage = await client.settings.get_usage()
            return retry_after_from_usage(usage, datetime.now(timezone.utc))
        except Exception as err:
            logger.warning("Could not read NotebookLM usage meter: %s", err)
            return None

    @_translate_errors
    async def get_quota_status(self) -> dict[str, Any]:
        """Return the live NotebookLM usage meter and account limits.

        Returns:
            Dictionary with usage windows, per-action availability, and notebook/source limits.
        """
        async with self._client() as client:
            usage = await client.settings.get_usage()
            limits = await client.settings.get_account_limits()
        summary = usage_to_dict(usage)
        summary["notebook_limit"] = limits.notebook_limit
        summary["source_limit"] = limits.source_limit
        return summary

    @_translate_errors
    async def get_source_limit(self) -> int | None:
        """Return the maximum number of sources allowed per notebook for this account.

        Returns:
            Source limit, or None when NotebookLM does not report it.
        """
        async with self._client() as client:
            limits = await client.settings.get_account_limits()
        return None if limits.source_limit is None else int(limits.source_limit)

    @_translate_errors
    async def create_notebook(self, title: str) -> str:
        """Create a new notebook in NotebookLM.

        Args:
            title: The title of the new notebook.

        Returns:
            The created notebook identifier string.
        """
        async with self._client() as client:
            logger.info("Creating notebook: %s", title)
            nb = await client.notebooks.create(title)
            logger.info("Created notebook with ID: %s", nb.id)
            return str(nb.id)

    @_translate_errors
    async def upload_source(self, notebook_id: str, file_path: str) -> str:
        """Upload a PDF source file to an existing notebook.

        Args:
            notebook_id: The notebook identifier.
            file_path: Filesystem path to the local PDF file.

        Returns:
            The uploaded source identifier string.
        """
        pdf_path = Path(file_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF source file does not exist: {file_path}")

        async with self._client() as client:
            logger.info("Uploading source %s to notebook %s", pdf_path.name, notebook_id)
            source = await client.sources.add_file(notebook_id, pdf_path)
            logger.info("Source uploaded: ID=%s", source.id)
            return str(source.id)

    @_translate_errors
    async def wait_source_ready(self, notebook_id: str, source_id: str, timeout_seconds: int = 180) -> None:
        """Wait until an uploaded source is fully processed by NotebookLM.

        Args:
            notebook_id: The notebook identifier.
            source_id: The source identifier.
            timeout_seconds: Maximum time to wait in seconds.
        """
        async with self._client() as client:
            logger.info("Waiting for source %s in notebook %s to be ready...", source_id, notebook_id)
            await asyncio.wait_for(
                client.sources.wait_until_ready(notebook_id, source_id),
                timeout=float(timeout_seconds),
            )
            logger.info("Source %s is ready.", source_id)

    @_translate_errors
    async def generate_quiz(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        difficulty: str | None = None,
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate a quiz from selected sources and wait for it to complete.

        Quizzes have no language parameter in NotebookLM; language is steered by the prompt.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for the quiz generation.
            difficulty: 'easy', 'medium', 'hard', or None for the NotebookLM default.
            options: Course generation options (None = defaults).

        Returns:
            The completed quiz artifact id.
        """
        instructions = prompt or "Generate multiple choice questions with 4 options and detailed rationale."
        async with self._client() as client:
            status = await client.artifacts.generate_quiz(
                notebook_id=notebook_id,
                source_ids=source_ids,
                instructions=instructions,
                difficulty=to_quiz_difficulty(difficulty),
                **generation_kwargs("quiz", options),
            )
            return await finish_generation(client, notebook_id, status, "quiz")

    @_translate_errors
    async def generate_flashcards(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        options: GenerationOptions | None = None,
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
            return await finish_generation(client, notebook_id, status, "flashcards")

    @_translate_errors
    async def generate_mind_map(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Generate a note-backed mind map (synchronous in NotebookLM).

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for mind map generation.
            language: Course language ('zh-TW', 'en', 'bilingual').

        Returns:
            The id of the note the mind map was saved to.

        Raises:
            IncompleteArtifactError: When NotebookLM returned no mind map note.
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
            raise IncompleteArtifactError("NotebookLM returned no mind map note")
        logger.info("Mind map saved as note %s", result.note_id)
        return str(result.note_id)

    @_translate_errors
    async def generate_audio(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate a Deep Dive audio overview and wait for it to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional customization prompt for audio discussion.
            language: Course language ('zh-TW', 'en', 'bilingual').
            options: Course generation options (None = defaults).

        Returns:
            The completed audio artifact id.
        """
        instructions = prompt or "Discuss key points, mechanisms, and exam takeaways."
        async with self._client() as client:
            status = await client.artifacts.generate_audio(
                notebook_id=notebook_id,
                source_ids=source_ids,
                language=to_nlm_language(language),
                instructions=instructions,
                **generation_kwargs("audio", options),
            )
            return await finish_generation(client, notebook_id, status, "audio")

    @_translate_errors
    async def generate_report(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        report_format: str = "briefing_doc",
    ) -> str:
        """Generate a report (briefing doc, study guide, blog post) and wait for it to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Course language ('zh-TW', 'en', 'bilingual').
            report_format: Format key (briefing_doc, study_guide, blog_post, concept_explanation).

        Returns:
            The completed report artifact id.
        """
        formats = {
            "study_guide": ReportFormat.STUDY_GUIDE,
            "blog_post": ReportFormat.BLOG_POST,
            "concept_explanation": ReportFormat.CONCEPT_EXPLANATION,
        }
        async with self._client() as client:
            status = await client.artifacts.generate_report(
                notebook_id=notebook_id,
                report_format=formats.get(report_format, ReportFormat.BRIEFING_DOC),
                source_ids=source_ids,
                language=to_nlm_language(language),
                custom_prompt=build_language_instruction(prompt, language),
            )
            return await finish_generation(client, notebook_id, status, f"report ({report_format})")

    @_translate_errors
    async def generate_slide_deck(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate a slide deck and wait for it to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Course language ('zh-TW', 'en', 'bilingual').
            options: Course generation options (None = defaults).

        Returns:
            The completed slide deck artifact id.
        """
        async with self._client() as client:
            status = await client.artifacts.generate_slide_deck(
                notebook_id=notebook_id,
                source_ids=source_ids,
                language=to_nlm_language(language),
                instructions=build_language_instruction(prompt, language),
                **generation_kwargs("slide_deck", options),
            )
            return await finish_generation(client, notebook_id, status, "slide deck")

    @_translate_errors
    async def generate_infographic(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate an infographic and wait for it to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Course language ('zh-TW', 'en', 'bilingual').
            options: Course generation options (None = defaults).

        Returns:
            The completed infographic artifact id.
        """
        async with self._client() as client:
            status = await client.artifacts.generate_infographic(
                notebook_id=notebook_id,
                source_ids=source_ids,
                language=to_nlm_language(language),
                instructions=build_language_instruction(prompt, language),
                **generation_kwargs("infographic", options),
            )
            return await finish_generation(client, notebook_id, status, "infographic")

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
            return await finish_generation(client, notebook_id, status, "data table")

    @_translate_errors
    async def generate_video(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate a video overview and wait for it to complete.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Course language ('zh-TW', 'en', 'bilingual').
            options: Course generation options (None = defaults).

        Returns:
            The completed video artifact id.
        """
        async with self._client() as client:
            status = await client.artifacts.generate_video(
                notebook_id=notebook_id,
                source_ids=source_ids,
                language=to_nlm_language(language),
                instructions=build_language_instruction(prompt, language),
                **generation_kwargs("video", options),
            )
            return await finish_generation(client, notebook_id, status, "video", timeout=1800.0)

    @_translate_errors
    async def download_artifact(
        self, kind: str, notebook_id: str, output_path: str, artifact_id: str, **extra: Any
    ) -> None:
        """Download one specific artifact with the notebooklm-py downloader for its kind.

        Args:
            kind: Downloader suffix (quiz, flashcards, mind_map, audio, report, slide_deck,
                infographic, data_table, video).
            notebook_id: The notebook identifier.
            output_path: Local filesystem destination.
            artifact_id: Artifact (or mind map note) id returned by the generate call.
            **extra: Extra downloader keywords (e.g. output_format for slide decks).
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with self._client() as client:
            logger.info("Downloading %s %s from notebook %s to %s", kind, artifact_id, notebook_id, out)
            downloader = getattr(client.artifacts, f"download_{kind}")
            await downloader(notebook_id, str(out), artifact_id=artifact_id, **extra)

    async def download_quiz(self, notebook_id: str, output_path: str, artifact_id: str | None = None) -> None:
        """Download a quiz JSON.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Artifact id returned by generate_quiz.
        """
        await self.download_artifact("quiz", notebook_id, output_path, artifact_id or "")

    async def download_flashcards(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download a flashcards JSON.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Artifact id returned by generate_flashcards.
        """
        await self.download_artifact("flashcards", notebook_id, output_path, artifact_id or "")

    async def download_mind_map(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download a mind map JSON.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Mind map note id returned by generate_mind_map.
        """
        await self.download_artifact("mind_map", notebook_id, output_path, artifact_id or "")

    async def download_audio(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download an audio overview (MP3/MP4 audio).

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where audio should be saved.
            artifact_id: Artifact id returned by generate_audio.
        """
        await self.download_artifact("audio", notebook_id, output_path, artifact_id or "")

    async def download_report(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download a report / study guide as Markdown.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Artifact id returned by generate_report.
        """
        await self.download_artifact("report", notebook_id, output_path, artifact_id or "")

    async def download_slide_deck(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None, output_format: str = "pdf"
    ) -> None:
        """Download a slide deck as PDF or PPTX.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Artifact id returned by generate_slide_deck.
            output_format: 'pdf' or 'pptx'.
        """
        await self.download_artifact(
            "slide_deck", notebook_id, output_path, artifact_id or "", output_format=output_format
        )

    async def download_infographic(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download an infographic image.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Artifact id returned by generate_infographic.
        """
        await self.download_artifact("infographic", notebook_id, output_path, artifact_id or "")

    async def download_data_table(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download a data table.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Artifact id returned by generate_data_table.
        """
        await self.download_artifact("data_table", notebook_id, output_path, artifact_id or "")

    async def download_video(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download a video overview.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Artifact id returned by generate_video.
        """
        await self.download_artifact("video", notebook_id, output_path, artifact_id or "")

    @_translate_errors
    async def rename_artifact(self, notebook_id: str, artifact_id: str, title: str) -> None:
        """Rename an artifact within NotebookLM for readability.

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
                logger.warning("Could not rename artifact %s on NotebookLM: %s", artifact_id, err)

    @_translate_errors
    async def rename_mind_map(self, notebook_id: str, note_id: str, title: str) -> None:
        """Rename a note-backed mind map within NotebookLM. Refs: ISSUE-011

        Mind maps are notes, not studio artifacts, so `artifacts.rename` cannot rename them.

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
            results: list[dict[str, Any]] = []
            for a in artifacts:
                kind_str = a.kind.value if hasattr(a.kind, "value") else str(a.kind)
                results.append(
                    {
                        "id": str(a.id),
                        "title": getattr(a, "title", None) or "Untitled",
                        "kind": kind_str.lower(),
                        "status": getattr(a, "status_str", "done"),
                        "is_completed": getattr(a, "is_completed", True),
                        "created_at": str(getattr(a, "created_at", "")),
                    }
                )
            return results

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
        async with self._client() as client:
            k = kind.lower()
            if "quiz" in k or "exam" in k:
                await client.artifacts.download_quiz(notebook_id, str(out), artifact_id=artifact_id)
            elif "flashcard" in k:
                await client.artifacts.download_flashcards(notebook_id, str(out), artifact_id=artifact_id)
            elif "audio" in k:
                await client.artifacts.download_audio(notebook_id, str(out), artifact_id=artifact_id)
            elif "report" in k or "briefing" in k or "study_guide" in k:
                await client.artifacts.download_report(notebook_id, str(out), artifact_id=artifact_id)
            elif "slide" in k:
                await client.artifacts.download_slide_deck(notebook_id, str(out), artifact_id=artifact_id)
            elif "infographic" in k:
                await client.artifacts.download_infographic(notebook_id, str(out), artifact_id=artifact_id)
            elif "mind_map" in k or "mindmap" in k:
                await client.artifacts.download_mind_map(notebook_id, str(out), artifact_id=artifact_id)
            elif "data_table" in k or "table" in k:
                await client.artifacts.download_data_table(notebook_id, str(out), artifact_id=artifact_id)
            elif "video" in k:
                await client.artifacts.download_video(notebook_id, str(out), artifact_id=artifact_id)
            else:
                await client.artifacts.download_report(notebook_id, str(out), artifact_id=artifact_id)
            return str(out)

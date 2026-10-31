"""NotebookLM API adapter: encapsulates NotebookLM client and maps exceptions to domain errors.

Provides resilient operations for uploading course PDFs, generating quizzes,
flashcards, mind maps, audio overviews, and downloading raw artifacts with
error translation for quota limits and authentication expiration.
"""

from __future__ import annotations

import asyncio
import functools
import logging
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

from notebooklm_batch_studio.config.settings import AppConfig, load_config
from notebooklm_batch_studio.domain.exceptions import (
    AuthExpiredError,
    IncompleteArtifactError,
    QuotaExceededError,
    StudioError,
)

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
            if mapped is not err:
                raise mapped from err
            logger.exception("Unexpected error communicating with NotebookLM: %s", err)
            raise

    return wrapper


class NotebookLMAdapter:
    """Adapter implementing NotebookLMClientProtocol using official notebooklm-py client."""

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

    def check_auth(self) -> bool:
        """Check whether local authentication credentials exist and are non-empty.

        Returns:
            True if credentials file exists and has content, False otherwise.
        """
        if self.storage_path.exists() and self.storage_path.stat().st_size > 0:
            return True
        return False

    @_translate_errors
    async def create_notebook(self, title: str) -> str:
        """Create a new notebook in NotebookLM.

        Args:
            title: The title of the new notebook.

        Returns:
            The created notebook identifier string.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
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

        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
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
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            logger.info("Waiting for source %s in notebook %s to be ready...", source_id, notebook_id)
            await asyncio.wait_for(
                client.sources.wait_until_ready(notebook_id, source_id),
                timeout=float(timeout_seconds),
            )
            logger.info("Source %s is ready.", source_id)

    @_translate_errors
    async def generate_quiz(self, notebook_id: str, source_ids: list[str], prompt: str | None = None) -> str:
        """Request generation of a quiz from selected sources.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for the quiz generation.

        Returns:
            The task identifier for tracking progress.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            logger.info("Generating quiz in notebook %s from %d sources", notebook_id, len(source_ids))
            instructions = (
                prompt or "Generate multiple choice questions with 4 options and detailed rationale."
            )
            status = await client.artifacts.generate_quiz(
                notebook_id=notebook_id,
                source_ids=source_ids,
                instructions=instructions,
            )
            task_id = getattr(status, "task_id", str(status))
            logger.info("Quiz task submitted: %s, waiting for completion...", task_id)
            await client.artifacts.wait_for_completion(notebook_id, task_id)
            return str(task_id)

    @_translate_errors
    async def download_quiz(self, notebook_id: str, output_path: str) -> None:
        """Download generated quiz JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            logger.info("Downloading quiz from notebook %s to %s", notebook_id, out)
            await client.artifacts.download_quiz(notebook_id, str(out))

    @_translate_errors
    async def generate_flashcards(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None
    ) -> str:
        """Request generation of flashcards from selected sources.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for flashcards generation.

        Returns:
            The task identifier for tracking progress.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            logger.info("Generating flashcards in notebook %s", notebook_id)
            instructions = prompt or "Extract key vocabulary, core concepts, and biochemical mechanisms."
            status = await client.artifacts.generate_flashcards(
                notebook_id=notebook_id,
                source_ids=source_ids,
                instructions=instructions,
            )
            task_id = getattr(status, "task_id", str(status))
            logger.info("Flashcards task submitted: %s, waiting for completion...", task_id)
            await client.artifacts.wait_for_completion(notebook_id, task_id)
            return str(task_id)

    @_translate_errors
    async def download_flashcards(self, notebook_id: str, output_path: str) -> None:
        """Download generated flashcards JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            logger.info("Downloading flashcards from notebook %s to %s", notebook_id, out)
            await client.artifacts.download_flashcards(notebook_id, str(out))

    @_translate_errors
    async def generate_mind_map(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None
    ) -> str:
        """Request generation of a mind map from selected sources.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for mind map generation.

        Returns:
            The task identifier or status string.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            logger.info("Generating mind map in notebook %s", notebook_id)
            instructions = prompt or "Create a detailed hierarchical mind map organizing concepts."
            status = await client.artifacts.generate_mind_map(
                notebook_id=notebook_id,
                source_ids=source_ids,
                instructions=instructions,
            )
            task_id = getattr(status, "task_id", str(status))
            logger.info("Mind map task submitted: %s", task_id)
            return str(task_id)

    @_translate_errors
    async def download_mind_map(self, notebook_id: str, output_path: str) -> None:
        """Download generated mind map JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            logger.info("Downloading mind map from notebook %s to %s", notebook_id, out)
            await client.artifacts.download_mind_map(notebook_id, str(out))

    @_translate_errors
    async def generate_audio(self, notebook_id: str, source_ids: list[str], prompt: str | None = None) -> str:
        """Request generation of Deep Dive Audio overview.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional customization prompt for audio discussion.

        Returns:
            Task identifier or status string for audio generation.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            logger.info("Generating audio overview in notebook %s", notebook_id)
            instructions = prompt or "Discuss key points, mechanisms, and exam takeaways."
            status = await client.artifacts.generate_audio(
                notebook_id=notebook_id,
                source_ids=source_ids,
                instructions=instructions,
            )
            task_id = getattr(status, "task_id", str(status))
            logger.info("Audio generation task submitted: %s", task_id)
            return str(task_id)

    @_translate_errors
    async def download_audio(self, notebook_id: str, output_path: str) -> None:
        """Download generated Audio MP3 file to local storage.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where MP3 should be saved.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            logger.info("Downloading audio overview from notebook %s to %s", notebook_id, out)
            await client.artifacts.download_audio(notebook_id, str(out))

    @_translate_errors
    async def rename_artifact(self, notebook_id: str, artifact_id: str, title: str) -> None:
        """Rename an artifact within NotebookLM for readability.

        Args:
            notebook_id: The notebook identifier.
            artifact_id: The artifact identifier to rename.
            title: The new title string (e.g. '[03] Quiz 1-基礎').
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            logger.info("Renaming artifact %s to '%s' in notebook %s", artifact_id, title, notebook_id)
            try:
                await client.artifacts.rename(notebook_id, artifact_id, title)
            except Exception as err:
                logger.warning("Could not rename artifact %s on NotebookLM: %s", artifact_id, err)

    @_translate_errors
    async def find_latest_artifact(self, notebook_id: str, artifact_type: str | None = None) -> str | None:
        """Find the most recently generated artifact ID in a notebook.

        Args:
            notebook_id: The notebook identifier.
            artifact_type: Optional filter string for artifact kind.

        Returns:
            Artifact ID string, or None if not found.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            arts = await client.artifacts.list(notebook_id)
            if not arts:
                return None
            sorted_arts = sorted(
                arts,
                key=lambda a: getattr(a, "created_at", None) or getattr(a, "last_modified_at", None) or "",
                reverse=True,
            )
            top = sorted_arts[0]
            return str(getattr(top, "id", "")) or None

    @_translate_errors
    async def generate_report(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        report_format: str = "briefing_doc",
    ) -> str:
        """Request generation of a report in NotebookLM.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language ('zh-TW', 'en', 'bilingual').
            report_format: Format key (briefing_doc, study_guide, blog_post).

        Returns:
            Task or artifact identifier.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            instructions = build_language_instruction(prompt, language)
            logger.info("Generating report (%s) in notebook %s", report_format, notebook_id)
            fmt_enum = ReportFormat.BRIEFING_DOC
            if report_format == "study_guide":
                fmt_enum = ReportFormat.STUDY_GUIDE
            elif report_format == "blog_post":
                fmt_enum = ReportFormat.BLOG_POST
            elif report_format == "concept_explanation":
                fmt_enum = ReportFormat.CONCEPT_EXPLANATION

            status = await client.artifacts.generate_report(
                notebook_id=notebook_id,
                report_format=fmt_enum,
                source_ids=source_ids,
                language="zh-TW" if language == "zh-TW" else "en",
                custom_prompt=instructions,
            )
            task_id = getattr(status, "task_id", str(status))
            return str(task_id)

    @_translate_errors
    async def wait_for_completion(
        self, notebook_id: str, task_id: str, timeout_seconds: int = 300
    ) -> None:
        """Wait for an artifact generation task to finish.

        Args:
            notebook_id: The notebook identifier.
            task_id: Task identifier.
            timeout_seconds: Maximum wait time.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            await client.artifacts.wait_for_completion(
                notebook_id=notebook_id,
                task_id=task_id,
                timeout=float(timeout_seconds),
            )

    @_translate_errors
    async def download_report(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download report/study guide content to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            await client.artifacts.download_report(notebook_id, str(out), artifact_id=artifact_id)

    @_translate_errors
    async def generate_slide_deck(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Request generation of slide deck presentation outline.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.

        Returns:
            Task or artifact identifier.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            instructions = build_language_instruction(prompt, language)
            logger.info("Generating slide deck in notebook %s", notebook_id)
            status = await client.artifacts.generate_slide_deck(
                notebook_id=notebook_id,
                source_ids=source_ids,
                instructions=instructions,
            )
            task_id = getattr(status, "task_id", str(status))
            return str(task_id)

    @_translate_errors
    async def download_slide_deck(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download slide deck outline to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            await client.artifacts.download_slide_deck(notebook_id, str(out), artifact_id=artifact_id)

    @_translate_errors
    async def generate_infographic(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Request generation of an infographic.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.

        Returns:
            Task or artifact identifier.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            instructions = build_language_instruction(prompt, language)
            logger.info("Generating infographic in notebook %s", notebook_id)
            status = await client.artifacts.generate_infographic(
                notebook_id=notebook_id,
                source_ids=source_ids,
                instructions=instructions,
            )
            task_id = getattr(status, "task_id", str(status))
            return str(task_id)

    @_translate_errors
    async def download_infographic(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download infographic to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            await client.artifacts.download_infographic(notebook_id, str(out), artifact_id=artifact_id)

    @_translate_errors
    async def generate_data_table(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Request generation of comparison data table.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.

        Returns:
            Task or artifact identifier.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            instructions = build_language_instruction(prompt, language)
            logger.info("Generating data table in notebook %s", notebook_id)
            status = await client.artifacts.generate_data_table(
                notebook_id=notebook_id,
                source_ids=source_ids,
                instructions=instructions,
            )
            task_id = getattr(status, "task_id", str(status))
            return str(task_id)

    @_translate_errors
    async def download_data_table(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download data table content to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            await client.artifacts.download_data_table(notebook_id, str(out), artifact_id=artifact_id)

    @_translate_errors
    async def generate_video(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Request generation of cinematic video overview.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.

        Returns:
            Task or artifact identifier.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            instructions = build_language_instruction(prompt, language)
            logger.info("Generating video in notebook %s", notebook_id)
            status = await client.artifacts.generate_video(
                notebook_id=notebook_id,
                source_ids=source_ids,
                instructions=instructions,
            )
            task_id = getattr(status, "task_id", str(status))
            return str(task_id)

    @_translate_errors
    async def download_video(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download generated video to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
            await client.artifacts.download_video(notebook_id, str(out), artifact_id=artifact_id)

    @_translate_errors
    async def list_artifacts(self, notebook_id: str) -> list[dict[str, Any]]:
        """List all remote artifacts present in a notebook.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            List of dictionary summaries of artifacts.
        """
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
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
        async with NotebookLMClient.from_storage(path=str(self.storage_path)) as client:
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

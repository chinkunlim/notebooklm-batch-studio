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
            await client.artifacts.rename(notebook_id, artifact_id, title)

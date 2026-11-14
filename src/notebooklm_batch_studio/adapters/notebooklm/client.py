"""Gemini Notebook API adapter: encapsulates Gemini Notebook client and maps exceptions to domain errors.

Provides resilient operations for uploading course PDFs, generating quizzes,
flashcards, mind maps, audio overviews, and downloading raw artifacts with
error translation for quota limits and authentication expiration.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from notebooklm import NotebookLMClient

from notebooklm_batch_studio.adapters.notebooklm.client_artifacts import ArtifactOperationsMixin
from notebooklm_batch_studio.adapters.notebooklm.downloads import ArtifactDownloadsMixin
from notebooklm_batch_studio.adapters.notebooklm.errors import (
    CONCEPT_EXPLANATION_DIRECTIVE as CONCEPT_EXPLANATION_DIRECTIVE,
)
from notebooklm_batch_studio.adapters.notebooklm.errors import (
    _translate_errors as _translate_errors,
)
from notebooklm_batch_studio.adapters.notebooklm.errors import (
    build_language_instruction as build_language_instruction,
)
from notebooklm_batch_studio.adapters.notebooklm.quota import retry_after_from_usage, usage_to_dict
from notebooklm_batch_studio.config.settings import AppConfig, load_config

logger = logging.getLogger(__name__)


class NotebookLMAdapter(ArtifactOperationsMixin, ArtifactDownloadsMixin):
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
        """Initialize the Gemini Notebook adapter.

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
            logger.warning("Could not read Gemini Notebook usage meter: %s", err)
            return None

    @_translate_errors
    async def get_quota_status(self) -> dict[str, Any]:
        """Return the live Gemini Notebook usage meter and account limits.

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
            Source limit, or None when Gemini Notebook does not report it.
        """
        async with self._client() as client:
            limits = await client.settings.get_account_limits()
        return None if limits.source_limit is None else int(limits.source_limit)

    @_translate_errors
    async def ask(self, notebook_id: str, question: str, source_ids: list[str] | None = None) -> str:
        """Ask the notebook a question grounded in its sources (Gemini Notebook chat).

        Args:
            notebook_id: Notebook identifier.
            question: Question text.
            source_ids: Limit the answer to these sources (None = all).

        Returns:
            The answer text.
        """
        async with self._client() as client:
            result = await client.chat.ask(notebook_id, question, source_ids=source_ids)
        return str(result.answer)

    @_translate_errors
    async def ask_in_conversation(
        self, notebook_id: str, question: str, source_ids: list[str] | None, conversation_id: str | None
    ) -> tuple[str, str | None]:
        """Ask a question that continues an earlier chat; the notebook's chat settings are not changed.

        Args:
            notebook_id: Notebook identifier.
            question: Question text.
            source_ids: Limit the answer to these sources (None = all).
            conversation_id: Conversation to continue, or None to start one.

        Returns:
            (answer text, conversation id for the next follow-up).
        """
        async with self._client() as client:
            result = await client.chat.ask(
                notebook_id, question, source_ids=source_ids, conversation_id=conversation_id
            )
        return str(result.answer), result.conversation_id

    @_translate_errors
    async def find_notebook_by_title(self, title: str) -> str | None:
        """Find an existing notebook whose title matches exactly (most recent first).

        Args:
            title: Notebook title, e.g. "[115-1] 心理學研究法".

        Returns:
            The notebook id, or None when there is no such notebook.
        """
        async with self._client() as client:
            notebooks = await client.notebooks.list()
        match = next((nb for nb in notebooks if nb.title == title), None)
        return str(match.id) if match else None

    @_translate_errors
    async def list_ready_sources(self, notebook_id: str) -> dict[str, str]:
        """Map the titles of a notebook's ready sources (the uploaded PDF file names) to their ids.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            Source title to source id, for sources that finished processing.
        """
        async with self._client() as client:
            sources = await client.sources.list(notebook_id)
        return {
            str(s.title): str(s.id) for s in sources if s.title and getattr(s.status, "name", "") == "READY"
        }

    @_translate_errors
    async def create_notebook(self, title: str) -> str:
        """Create a new notebook in Gemini Notebook.

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
        """Wait until an uploaded source is fully processed by Gemini Notebook.

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

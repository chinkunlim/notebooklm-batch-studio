"""NotebookLM fallback driver for modular Markdown note generation (Refs: ADR-012).

Wraps `NotebookLMAdapter.ask_in_conversation` so the modular 7-step note pipeline
can target an existing Gemini Notebook and single-chapter `source_id` as a
fallback backend when Gemini Web is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter

logger = logging.getLogger(__name__)


class NotebookLMNoteDriver:
    """Synchronous driver adapting NotebookLMAdapter for modular note generation."""

    def __init__(
        self,
        client: NotebookLMAdapter,
        notebook_id: str,
        source_ids: list[str] | None = None,
    ) -> None:
        """Initialize the NotebookLM note driver.

        Args:
            client: Authenticated NotebookLMAdapter instance.
            notebook_id: Target Gemini Notebook ID.
            source_ids: Source IDs to scope answers to (single chapter PDF).
        """
        self._client = client
        self._notebook_id = notebook_id
        self._source_ids = list(source_ids) if source_ids else None
        self._conversation_id: str | None = None
        self.last_read_source: str = "notebooklm_api"
        self.was_dom_fallback: bool = False

    def open_chapter_chat(self, title: str = "") -> None:
        """Reset conversation state to start a fresh chapter chat.

        Args:
            title: Chapter title (logged for traceability).
        """
        self._conversation_id = None
        logger.info("Opened NotebookLM note chat for notebook=%s title=%s", self._notebook_id, title)

    def set_model(self, model_name: str) -> None:
        """No-op model selector for NotebookLM (model is managed server-side).

        Args:
            model_name: Requested model name.
        """
        logger.debug("NotebookLM backend ignores client-side model=%s", model_name)

    def set_thinking_level(self, level: str) -> None:
        """No-op thinking level selector for NotebookLM.

        Args:
            level: Requested thinking level.
        """
        logger.debug("NotebookLM backend ignores thinking_level=%s", level)

    def upload_files(self, paths: list[Path]) -> None:
        """Verify source scoping instead of uploading files via browser UI.

        Args:
            paths: Local file paths (ignored; NotebookLM uses pre-uploaded source_ids).
        """
        logger.debug(
            "NotebookLM note driver uses source_ids=%s (skipping %d local file uploads)",
            self._source_ids,
            len(paths),
        )

    def rename_chat(self, title: str) -> bool:
        """No-op chat rename for NotebookLM API conversations.

        Args:
            title: Desired conversation title.

        Returns:
            Always True.
        """
        logger.debug("NotebookLM note driver skips chat rename (%s)", title)
        return True

    def send_prompt_and_read(self, prompt: str, **kwargs: Any) -> str:
        """Send one module prompt to NotebookLM and return the Markdown reply.

        Args:
            prompt: Rendered prompt text for the current module step.
            **kwargs: Ignored Gemini Web options such as `expected_model` or `timeout_seconds`.

        Returns:
            Markdown reply from NotebookLM.
        """
        del kwargs
        answer, conv_id = asyncio.run(
            self._client.ask_in_conversation(
                self._notebook_id,
                prompt,
                source_ids=self._source_ids,
                conversation_id=self._conversation_id,
            )
        )
        if conv_id:
            self._conversation_id = conv_id
        return str(answer)

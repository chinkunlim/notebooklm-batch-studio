"""Local Ollama client adapter for prompt enhancement and academic synthesis.

Communicates with the local Ollama instance on http://127.0.0.1:11434 (never 0.0.0.0 or localhost).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig, load_config

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for local Ollama LLM generation (e.g. gemma4:latest)."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str = "gemma4:latest",
        timeout_seconds: float = 30.0,
        config: AppConfig | None = None,
    ) -> None:
        """Initialize Ollama adapter.

        Args:
            base_url: Ollama base endpoint (defaults to config or http://127.0.0.1:11434).
            model: Model tag on local Ollama.
            timeout_seconds: Request timeout in seconds.
            config: Optional application configuration.
        """
        cfg = config or load_config()
        self.base_url = (base_url or cfg.ollama_base_url).rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        """Check whether local Ollama service is reachable.

        Returns:
            True if service responds to /api/tags, False otherwise.
        """
        url = f"{self.base_url}/api/tags"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "notebooklm-batch-studio"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return bool(resp.status == 200)
        except Exception:
            return False

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate text completion from Ollama.

        Args:
            prompt: User prompt content.
            system_prompt: Optional system prompt context.

        Returns:
            Completed text string, or empty string on failure.
        """
        url = f"{self.base_url}/api/generate"
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "notebooklm-batch-studio"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    return str(body.get("response", "")).strip()
        except urllib.error.URLError as err:
            logger.warning("Ollama connection error at %s: %s", url, err)
        except Exception as err:
            logger.exception("Unexpected error calling Ollama: %s", err)

        return ""

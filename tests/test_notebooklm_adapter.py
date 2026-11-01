"""Offline unit tests for Gemini Notebook adapter and error translation logic.

Tests authentication checking, exception translation for rate limits (QuotaExceededError),
session expiry (AuthExpiredError), and artifact failure (IncompleteArtifactError).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from notebooklm import ArtifactTimeoutError, AuthError, RateLimitError

from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter, _translate_errors
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import (
    AuthExpiredError,
    IncompleteArtifactError,
    QuotaExceededError,
)


class TestNotebookLMAdapter(unittest.IsolatedAsyncioTestCase):
    """Test suite for NotebookLMAdapter and error translation."""

    def setUp(self) -> None:
        """Set up test environment with temporary paths."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.storage_file = self.tmp_path / "storage_state.json"

        self.config = AppConfig(
            data_dir=self.tmp_path / "data",
            notebooklm_home=self.tmp_path / "config",
        )
        self.adapter = NotebookLMAdapter(
            config=self.config,
            storage_path=self.storage_file,
        )

    def tearDown(self) -> None:
        """Clean up temporary test directory."""
        self.tmpdir.cleanup()

    def test_check_auth_missing_file(self) -> None:
        """Verify check_auth returns False when storage file does not exist."""
        self.assertFalse(self.adapter.check_auth())

    def test_check_auth_existing_file(self) -> None:
        """Verify check_auth returns True when storage file exists with content."""
        self.storage_file.write_text('{"cookies": []}', encoding="utf-8")
        self.assertTrue(self.adapter.check_auth())

    async def test_translate_rate_limit_error(self) -> None:
        """Verify RateLimitError is caught and re-raised as domain QuotaExceededError."""

        @_translate_errors
        async def mock_fail() -> None:
            raise RateLimitError("Rate limit exceeded for audio generation")

        with self.assertRaises(QuotaExceededError) as ctx:
            await mock_fail()

        self.assertIn("quota or rate limit reached", str(ctx.exception))
        self.assertEqual(ctx.exception.retry_after_seconds, 3600)

    async def test_translate_auth_error(self) -> None:
        """Verify AuthError is caught and re-raised as domain AuthExpiredError."""

        @_translate_errors
        async def mock_auth_fail() -> None:
            raise AuthError("Session expired, please re-authenticate")

        with self.assertRaises(AuthExpiredError) as ctx:
            await mock_auth_fail()

        self.assertIn("credentials invalid or expired", str(ctx.exception))

    async def test_translate_artifact_timeout_error(self) -> None:
        """Verify ArtifactTimeoutError is translated to domain IncompleteArtifactError."""

        @_translate_errors
        async def mock_timeout() -> None:
            raise ArtifactTimeoutError("nb-test", "task-test", 180.0)

        with self.assertRaises(IncompleteArtifactError) as ctx:
            await mock_timeout()

        self.assertIn("Artifact generation incomplete", str(ctx.exception))

    async def test_translate_http_429_string_error(self) -> None:
        """Verify generic Exception containing HTTP 429 is converted to QuotaExceededError."""

        @_translate_errors
        async def mock_http_429() -> None:
            raise RuntimeError("HTTP 429 Too Many Requests: quota exceeded")

        with self.assertRaises(QuotaExceededError):
            await mock_http_429()

    async def test_translate_http_401_string_error(self) -> None:
        """Verify generic Exception containing HTTP 401 is converted to AuthExpiredError."""

        @_translate_errors
        async def mock_http_401() -> None:
            raise RuntimeError("HTTP 401 Unauthorized: token revoked")

        with self.assertRaises(AuthExpiredError):
            await mock_http_401()


if __name__ == "__main__":
    unittest.main()

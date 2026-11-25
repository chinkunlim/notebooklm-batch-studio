"""Real-Chrome sign-in for Gemini Notebook, replacing notebooklm-py's Playwright login (Refs: SPEC-022).

Google refuses sign-in in a browser that Playwright started. Like the Gemini web sign-in (ISSUE-053),
Chrome is started normally on its own profile in `DATA_DIR/state/notebooklm_chrome_profile`; once a
tab reaches notebook.google.com with Google auth cookies, CDP attaches briefly to save the session.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.gemini.auth_runtime import ChromeGeminiLoginRuntime
from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.services.notebook_login import NotebookLoginService

logger = logging.getLogger(__name__)

NOTEBOOK_URL = "https://notebook.google.com/"  # the old notebooklm domain only redirects here


class ChromeNotebookLoginRuntime(ChromeGeminiLoginRuntime):
    """Same real-Chrome flow as Gemini web, watching notebook.google.com instead."""

    start_url = NOTEBOOK_URL
    tab_prefix = NOTEBOOK_URL

    @staticmethod
    def is_page_signed_in(page: Any) -> bool:
        """Return True when the tab shows Gemini Notebook (signed-out users land on accounts.google.com).

        Args:
            page: Playwright Page instance.

        Returns:
            True for a notebook.google.com page.
        """
        return str(page.url or "").startswith(NOTEBOOK_URL)


def verify_notebooklm_storage(config: AppConfig, storage_path: Path) -> bool:
    """Check a session file by reading the Gemini Notebook usage meter with it (read-only, no quota used).

    Runs in a worker thread so it also works when called from inside an event loop (MCP).

    Args:
        config: Application configuration.
        storage_path: Session file to check.

    Returns:
        True when Gemini Notebook accepts the session.
    """
    adapter = NotebookLMAdapter(config, storage_path=storage_path)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, adapter.get_quota_status()).result(timeout=60)
        return True
    except Exception as exc:
        logger.warning("New Gemini Notebook session failed verification: %s", type(exc).__name__)
        return False


def build_notebook_login_service(config: AppConfig) -> NotebookLoginService:
    """Wire the real-Chrome runtime, the queue's session path, and live verification.

    Args:
        config: Application configuration.

    Returns:
        Ready `NotebookLoginService`.
    """
    runtime = ChromeNotebookLoginRuntime(config.notebooklm_chrome_profile_dir, config.chrome_path)
    storage = NotebookLMAdapter(config).storage_path
    return NotebookLoginService(storage, runtime, lambda path: verify_notebooklm_storage(config, path))

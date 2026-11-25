"""Gemini Notebook sign-in through real Chrome: save to a temp file, verify, then replace (Refs: SPEC-022).

The user signs in personally in a Chrome window the program starts normally (no Playwright attached),
so Google does not block it. The new session is only kept when Gemini Notebook accepts it; a timeout or
a rejected session never overwrites the working one. The program never sees or stores the password.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class LoginInProgressError(RuntimeError):
    """Raised when a Chrome sign-in is already waiting for the user."""


class ChromeLoginRuntimeProtocol(Protocol):
    """Opens real Chrome and writes `storage_state.json` once the user has signed in."""

    def run_browser_login(self, storage_state_path: Path, timeout_seconds: int) -> None:
        """Open Chrome, wait for the sign-in, and save the session to `storage_state_path`.

        Args:
            storage_state_path: Where to save the session.
            timeout_seconds: Longest wait for the user.
        """
        ...


class NotebookLoginService:
    """Run one Chrome sign-in at a time and keep the session only when it works."""

    def __init__(
        self, storage_path: Path, runtime: ChromeLoginRuntimeProtocol, verify: Callable[[Path], bool]
    ) -> None:
        """Bind where the session lives, how Chrome is driven, and how a session is checked.

        Args:
            storage_path: notebooklm-py `storage_state.json` used by the queue.
            runtime: Real-Chrome sign-in runtime.
            verify: Returns True when Gemini Notebook accepts the session file at the given path.
        """
        self.storage_path = storage_path
        self.runtime = runtime
        self.verify = verify
        self._lock = threading.Lock()

    def login(self, timeout_seconds: int = 300) -> dict[str, Any]:
        """Open Chrome for the user to sign in, then verify and keep the new session.

        Args:
            timeout_seconds: Longest wait for the user to finish signing in.

        Returns:
            `{"status": "signed_in" | "timeout" | "not_verified", "message": str}` (never cookies).

        Raises:
            LoginInProgressError: When another sign-in is still waiting.
        """
        if not self._lock.acquire(blocking=False):
            raise LoginInProgressError("已有一個 Gemini Notebook 登入視窗在等待登入")
        temp = self.storage_path.with_name(self.storage_path.name + ".new")
        try:
            logger.info("Gemini Notebook Chrome sign-in started (timeout %ds)", timeout_seconds)
            temp.unlink(missing_ok=True)
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.runtime.run_browser_login(temp, timeout_seconds)
            return self._keep_if_valid(temp)
        finally:
            temp.unlink(missing_ok=True)
            self._lock.release()

    def _keep_if_valid(self, temp: Path) -> dict[str, Any]:
        """Replace the stored session with `temp` when Gemini Notebook accepts it.

        Args:
            temp: Session file Chrome just wrote.

        Returns:
            Result dictionary for `login`.
        """
        if not temp.is_file():
            logger.warning("Gemini Notebook sign-in not finished in time")
            return {"status": "timeout", "message": "沒有在時間內完成登入，原本的登入資訊沒有變動。"}
        if not self.verify(temp):
            logger.warning("Gemini Notebook rejected the new session; keeping the old one")
            return {"status": "not_verified", "message": "登入未完成：Gemini Notebook 不接受這次的登入資訊。"}
        os.chmod(temp, 0o600)
        os.replace(temp, self.storage_path)
        logger.info("Gemini Notebook sign-in verified and saved")
        return {"status": "signed_in", "message": "已登入 Gemini Notebook。"}

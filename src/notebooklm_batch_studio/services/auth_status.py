"""Read-only three-profile sign-in status overview without exposing credential contents (SPEC-014 Task 14)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol

from notebooklm_batch_studio.config.settings import AppConfig

logger = logging.getLogger(__name__)


class GeminiAuthStatusProtocol(Protocol):
    """Subset of GeminiAuthService required for non-intrusive sign-in status checks."""

    def check_auth_status(self, live_check: bool = False) -> dict[str, Any]:
        """Inspect Gemini Web session metadata.

        Args:
            live_check: Whether to probe live remote endpoint.

        Returns:
            Dictionary containing `logged_in` boolean flag.
        """
        ...


def _notebooklm_state(home: Path) -> str:
    """Return `ready` when NotebookLM credential file exists, otherwise `missing` (never reads bytes).

    Args:
        home: `config.notebooklm_home` directory.

    Returns:
        `'ready'` or `'missing'`.
    """
    candidates = (home / "profiles" / "default" / "storage_state.json", home / "storage_state.json")
    return "ready" if any(p.is_file() for p in candidates) else "missing"


def _gemini_web_state(profile_dir: Path, gemini_auth: GeminiAuthStatusProtocol) -> str:
    """Evaluate Gemini Web session state using `check_auth_status(live_check=False)`.

    Args:
        profile_dir: `config.gemini_profile_dir` directory.
        gemini_auth: Configured `GeminiAuthService`.

    Returns:
        `'ready'`, `'expired'`, or `'missing'`.
    """
    info = gemini_auth.check_auth_status(live_check=False)
    if info.get("logged_in"):
        return "ready"
    if (profile_dir / "storage_state.json").is_file():
        return "expired"
    return "missing"


def _library_profile_state(profile_dir: Path) -> str:
    """Return `ready` when library browser profile folder has files, else `missing` (never reads files).

    Args:
        profile_dir: `config.literature_browser_profile_dir` directory.

    Returns:
        `'ready'` or `'missing'`.
    """
    if not profile_dir.is_dir():
        return "missing"
    try:
        has_entry = any(True for _ in profile_dir.iterdir())
    except OSError:
        return "missing"
    return "ready" if has_entry else "missing"


def sign_in_status(config: AppConfig, gemini_auth: GeminiAuthStatusProtocol) -> list[dict[str, str]]:
    """Summarize authentication readiness across NotebookLM, Gemini Web, and Literature browser profiles.

    Checks NotebookLM and Library browser profiles strictly by file/directory existence without
    reading cookie or token contents.

    Args:
        config: Application configuration.
        gemini_auth: Configured Gemini Web auth service.

    Returns:
        Three-item list of dictionaries `{name, location, state, how_to_sign_in}`; rows that can
        sign in from the web also carry `login_route`.
    """
    rows = [
        {
            "name": "NotebookLM",
            "location": str(config.notebooklm_home),
            "state": _notebooklm_state(config.notebooklm_home),
            "how_to_sign_in": "按「登入」開啟 Chrome 親自登入 Google（或 CLI：login --browser）",
            "login_route": "/api/notebooklm/login",  # SPEC-022: real Chrome, not Playwright
        },
        {
            "name": "Gemini 網頁",
            "location": str(config.gemini_profile_dir),
            "state": _gemini_web_state(config.gemini_profile_dir, gemini_auth),
            "how_to_sign_in": "在網頁「筆記生成 → 登入 Gemini」或 POST /api/notes/gemini/login",
        },
        {
            "name": "文獻／圖書館瀏覽器",
            "location": str(config.literature_browser_profile_dir),
            "state": _library_profile_state(config.literature_browser_profile_dir),
            "how_to_sign_in": (
                "設定 .env 的 LIBRARY_EMAIL / LIBRARY_PASSWORD 後，下載需認證 PDF 時透過瀏覽器登入"
            ),
        },
    ]
    logger.debug("Evaluated sign-in status across 3 profiles: %s", [r["state"] for r in rows])
    return rows

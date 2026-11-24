"""Gemini Web authentication status and session persistence service (Refs: ISSUE-053).

Manages storage_state validity checks, local retention configuration, live session
probing, and logout cleanup for the `gemini_web` note generation backend. Actual
real-Chrome launch and Playwright CDP attachment live in `adapters/gemini/auth_runtime.py`.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from notebooklm_batch_studio.config.settings import load_config

logger = logging.getLogger(__name__)

# Essential Google login cookies that confirm an active user session (note-studio SPEC-013).
GOOGLE_AUTH_COOKIE_NAMES = frozenset(
    {
        "SID",
        "HSID",
        "SSID",
        "APISID",
        "SAPISID",
        "__Secure-1PSID",
        "__Secure-3PSID",
    }
)


class GeminiLoginRuntimeProtocol(Protocol):
    """Adapter contract for interactive real-Chrome login without layer violations."""

    def is_chrome_running(self) -> bool:
        """Return True if the dedicated Gemini login Chrome process is open."""
        ...

    def chrome_user_data_dir(self) -> Path:
        """Return path to the dedicated Chrome user-data directory."""
        ...

    def run_browser_login(self, storage_state_path: Path, timeout_seconds: int) -> None:
        """Launch real Chrome on the Gemini profile and persist session state once signed in.

        Args:
            storage_state_path: Destination JSON file for Playwright storage_state cookies.
            timeout_seconds: Maximum wait time for interactive sign-in.
        """
        ...


class GeminiAuthService:
    """Manages Gemini Web authentication checks, retention policy, and login orchestration."""

    def __init__(
        self,
        data_dir: Path | None = None,
        chrome_path: str | None = None,
        login_runtime: GeminiLoginRuntimeProtocol | None = None,
    ) -> None:
        """Initialize GeminiAuthService.

        Args:
            data_dir: Base data directory (defaults to `load_config().data_dir`).
            chrome_path: Chrome executable path (defaults to `load_config().chrome_path`).
            login_runtime: Optional Chrome/Playwright adapter implementing `GeminiLoginRuntimeProtocol`.
        """
        cfg = load_config() if (data_dir is None or chrome_path is None) else None
        self.data_dir = data_dir if data_dir is not None else cfg.data_dir  # type: ignore[union-attr]
        self.chrome_path = chrome_path if chrome_path is not None else cfg.chrome_path  # type: ignore[union-attr]
        self.profile_dir = self.data_dir / "state" / "gemini_profile"
        self.storage_state_path = self.profile_dir / "storage_state.json"
        self.retention_config_path = self.profile_dir / "retention.json"
        self._login_runtime = login_runtime
        logger.debug("GeminiAuthService initialized with storage at %s", self.storage_state_path)

    def get_storage_state_path(self) -> Path:
        """Get the storage state JSON file path.

        Returns:
            Path pointing to `storage_state.json`.
        """
        return self.storage_state_path

    def get_retention_days(self) -> int:
        """Get configured local retention days for Gemini session cookies.

        Returns:
            Retention days integer (default 30; 0 keeps session until Google expires).
        """
        if not self.retention_config_path.exists():
            return 30
        try:
            data = json.loads(self.retention_config_path.read_text(encoding="utf-8"))
            return int(data.get("retention_days", 30))
        except Exception as exc:
            logger.warning("Failed to read Gemini retention config: %s", exc)
            return 30

    def set_retention_days(self, retention_days: int) -> dict[str, Any]:
        """Save session cookie retention policy.

        Args:
            retention_days: Days to retain local cookies (0 follows Google default).

        Returns:
            Confirmation dictionary with `success`, `retention_days`, and `message`.
        """
        self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.profile_dir, 0o700)
        days = max(0, retention_days)
        self.retention_config_path.write_text(
            json.dumps({"retention_days": days}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Updated Gemini session retention policy to %d days", days)
        msg = f"已成功更新憑證保留期限為 {days} 天" if days > 0 else "已設定為跟隨 Google 帳號預設期限"
        return {"success": True, "retention_days": days, "message": msg}

    @staticmethod
    def _inspect_cookies_validity(cookies: list[dict[str, Any]], current_ts: float) -> tuple[bool, int]:
        """Inspect cookies for active Google auth cookies and count non-expired entries.

        Args:
            cookies: Parsed cookie dictionaries from `storage_state.json`.
            current_ts: Current epoch timestamp in seconds.

        Returns:
            Tuple of `(has_google_auth_cookie, valid_cookie_count)`.
        """
        auth_found = False
        valid_count = 0
        for cookie in cookies:
            c_expires = cookie.get("expires", -1)
            if isinstance(c_expires, (int, float)) and c_expires > 0 and c_expires < current_ts:
                continue
            valid_count += 1
            if "google.com" in str(cookie.get("domain", "")) and str(cookie.get("name", "")) in (
                GOOGLE_AUTH_COOKIE_NAMES
            ):
                auth_found = True
        return auth_found, valid_count

    @staticmethod
    def _compute_retention(
        mtime: float, retention_days: int, current_ts: float
    ) -> tuple[bool, str, int | None]:
        """Calculate local retention expiry and remaining days.

        Args:
            mtime: File modification timestamp of `storage_state.json`.
            retention_days: Configured retention days.
            current_ts: Current epoch timestamp in seconds.

        Returns:
            Tuple of `(is_expired, expires_at_iso, days_remaining)`.
        """
        if retention_days <= 0:
            return False, "", None
        expire_ts = mtime + retention_days * 86400
        expires_at = datetime.datetime.fromtimestamp(expire_ts, tz=datetime.timezone.utc).isoformat()
        diff_sec = expire_ts - current_ts
        if diff_sec <= 0:
            return True, expires_at, 0
        return False, expires_at, int(diff_sec // 86400) + 1

    def _build_live_probe_cookie_header(self) -> str | None:
        """Build a Cookie header from saved Google/Gemini domain cookies.

        Returns:
            Cookie header string, or None when unavailable.
        """
        if not self.storage_state_path.exists():
            return None
        data = json.loads(self.storage_state_path.read_text(encoding="utf-8"))
        valid_domains = {".google.com", "google.com", "gemini.google.com", ".gemini.google.com"}
        parts = [
            f"{c['name']}={c['value']}" for c in data.get("cookies", []) if c.get("domain") in valid_domains
        ]
        return "; ".join(parts) if parts else None

    def verify_live_session(self, timeout_seconds: float = 4.0) -> bool:
        """Actively probe `https://gemini.google.com/app` using saved session cookies.

        Args:
            timeout_seconds: HTTP request timeout in seconds.

        Returns:
            True if the session is actively signed in on Gemini, False otherwise.
        """
        cookie_header = self._build_live_probe_cookie_header()
        if not cookie_header:
            return False
        user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        )
        req = urllib.request.Request(
            "https://gemini.google.com/app",
            headers={"User-Agent": user_agent, "Cookie": cookie_header},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:  # noqa: S310 - fixed HTTPS URL
                final_url = resp.geturl()
                if any(k in final_url for k in ("accounts.google.com", "CookieMismatch", "ServiceLogin")):
                    return False
                body = bytes(resp.read()).decode("utf-8", errors="ignore")
                return "SignOutOptions" in body
        except Exception as exc:
            logger.warning("Gemini live session probe failed: %s", exc)
            return False

    def _evaluate_storage_state(self, default_res: dict[str, Any], live_check: bool) -> dict[str, Any]:
        """Parse `storage_state.json`, check retention expiry, and optionally probe live session.

        Args:
            default_res: Base status dictionary representing logged-out defaults.
            live_check: Whether to perform a live HTTP probe against Gemini.

        Returns:
            Populated authentication status dictionary.
        """
        mtime = self.storage_state_path.stat().st_mtime
        updated_at = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat()
        data = json.loads(self.storage_state_path.read_text(encoding="utf-8"))
        now_ts = time.time()
        auth_found, valid_cookies = self._inspect_cookies_validity(data.get("cookies", []), now_ts)
        expired, expires_at, days_rem = self._compute_retention(mtime, default_res["retention_days"], now_ts)

        if expired and auth_found:
            logger.info("Gemini session expired (%d days)", default_res["retention_days"])
            self.logout()
            default_res.update(
                updated_at=updated_at, expires_at=expires_at, days_remaining=0, reason="retention_expired"
            )
            return default_res
        if live_check and auth_found and not self.verify_live_session():
            # Keep storage_state on transient probe failures (note-studio ISSUE-030).
            logger.info("Gemini live probe failed or session requires re-verification.")
            default_res.update(logged_in=False, updated_at=updated_at, reason="session_invalidated")
            return default_res
        default_res.update(
            logged_in=auth_found,
            updated_at=updated_at,
            cookie_count=valid_cookies,
            expires_at=expires_at,
            days_remaining=days_rem,
        )
        return default_res

    def check_auth_status(self, live_check: bool = False) -> dict[str, Any]:
        """Check current Gemini Web authentication status.

        Args:
            live_check: Whether to perform a live HTTP verification probe.

        Returns:
            Status dictionary with `logged_in`, `updated_at`, `cookie_count`,
            `retention_days`, `expires_at`, `days_remaining`, and `storage_state_path`.
        """
        default_res: dict[str, Any] = {
            "logged_in": False,
            "updated_at": "",
            "cookie_count": 0,
            "retention_days": self.get_retention_days(),
            "expires_at": "",
            "days_remaining": None,
            "storage_state_path": str(self.storage_state_path),
        }
        if not self.storage_state_path.exists():
            return default_res
        try:
            return self._evaluate_storage_state(default_res, live_check)
        except Exception as exc:
            logger.warning("Failed to parse storage_state file %s: %s", self.storage_state_path, exc)
            return default_res

    def logout(self) -> dict[str, Any]:
        """Clear saved Gemini Chrome profile and local `storage_state.json`.

        Returns:
            Result dictionary with `success`, `logged_in`, and `message`.
        """
        logger.info("Clearing Gemini session at %s", self.storage_state_path)
        if self._login_runtime is not None and self._login_runtime.is_chrome_running():
            return {
                "success": False,
                "logged_in": True,
                "message": "Gemini 的 Chrome 視窗還開著，請先關閉該 Chrome 再登出。",
            }
        chrome_dir = (
            self._login_runtime.chrome_user_data_dir()
            if self._login_runtime is not None
            else self.profile_dir / "chrome_user_data"
        )
        if chrome_dir.exists():
            shutil.rmtree(chrome_dir, ignore_errors=True)
        if self.storage_state_path.exists():
            try:
                self.storage_state_path.unlink()
            except Exception as exc:
                logger.warning("Failed to remove storage_state file %s: %s", self.storage_state_path, exc)
                return {"success": False, "logged_in": True, "message": f"登出失敗: {exc}"}
        return {
            "success": True,
            "logged_in": False,
            "message": "已成功登出 Gemini 會話並清除本機憑證。",
        }

    def _check_login_prereqs(self) -> dict[str, Any] | None:
        """Verify runtime adapter and Playwright availability before opening Chrome.

        Returns:
            Failure response dictionary when a prerequisite is missing, otherwise None.
        """
        if self._login_runtime is None:
            return {
                "success": False,
                "logged_in": False,
                "message": "尚未設定 Chrome 登入執行器，無法開啟登入視窗。",
            }
        try:
            import playwright  # noqa: F401
        except ImportError as exc:
            logger.error("Playwright is not installed: %s", exc)
            return {
                "success": False,
                "logged_in": False,
                "message": "Playwright 未安裝，請執行 `uv add playwright`。",
            }
        return None

    def login_interactive(self, timeout_seconds: int = 300) -> dict[str, Any]:
        """Open real Google Chrome for manual Google/Gemini sign-in and save session state.

        Args:
            timeout_seconds: Maximum wait time in seconds for manual login.

        Returns:
            Result dictionary containing `success`, `logged_in`, `message`, `updated_at`,
            and `storage_state_path`.
        """
        prereq_err = self._check_login_prereqs()
        if prereq_err is not None:
            return prereq_err
        assert self._login_runtime is not None

        logger.info("Starting interactive Gemini login in real Chrome (timeout=%ds)", timeout_seconds)
        try:
            self._login_runtime.run_browser_login(self.storage_state_path, timeout_seconds)
        except Exception as exc:
            logger.error("Error during interactive Gemini login: %s", exc)
            return {"success": False, "logged_in": False, "message": f"登入過程發生錯誤: {exc}"}

        status = self.check_auth_status(live_check=False)
        logged_in = bool(status["logged_in"])
        msg = "Gemini 登入成功並已儲存會話。" if logged_in else "未完成 Google 登入（視窗已關閉或等待逾時）。"
        return {
            "success": logged_in,
            "logged_in": logged_in,
            "message": msg,
            "updated_at": status.get("updated_at", ""),
            "storage_state_path": str(self.storage_state_path),
        }

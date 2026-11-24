"""Chrome & Playwright CDP login runtime for Gemini Web auth (Refs: ISSUE-053).

Starts real Google Chrome on `DATA_DIR/state/gemini_profile/chrome_user_data/` without
Playwright attached so Google sign-in succeeds (note-studio ISSUE-039), then attaches
briefly over CDP once a tab reaches `gemini.google.com` to save `storage_state.json`.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.gemini import chrome_session
from notebooklm_batch_studio.adapters.private_dir import ensure_private_dir
from notebooklm_batch_studio.services.notes.gemini_auth_service import GOOGLE_AUTH_COOKIE_NAMES

logger = logging.getLogger(__name__)


def _is_valid_auth_cookie(cookie: dict[str, Any], current_ts: float) -> bool:
    """Return True if a cookie dictionary is a non-expired Google auth cookie.

    Args:
        cookie: Playwright cookie dictionary.
        current_ts: Current epoch timestamp.

    Returns:
        Boolean indicating whether the cookie proves Google authentication.
    """
    c_expires = cookie.get("expires", -1)
    if isinstance(c_expires, (int, float)) and 0 < c_expires < current_ts:
        return False
    return "google.com" in str(cookie.get("domain", "")) and str(cookie.get("name", "")) in (
        GOOGLE_AUTH_COOKIE_NAMES
    )


class ChromeGeminiLoginRuntime:
    """Real-Chrome login adapter implementing `GeminiLoginRuntimeProtocol`."""

    def __init__(self, profile_dir: Path, chrome_path: str) -> None:
        """Initialize the login runtime.

        Args:
            profile_dir: Directory containing `gemini_profile`.
            chrome_path: Path to Google Chrome executable.
        """
        self.profile_dir = profile_dir
        self.chrome_path = chrome_path

    def chrome_user_data_dir(self) -> Path:
        """Return Chrome user-data folder path inside `profile_dir`.

        Returns:
            Path to `chrome_user_data`.
        """
        return chrome_session.chrome_user_data_dir(self.profile_dir)

    def is_chrome_running(self) -> bool:
        """Return True if Chrome is currently active on this Gemini profile.

        Returns:
            Boolean indicating an active Chrome debugging port.
        """
        return chrome_session.running_port(self.chrome_user_data_dir()) is not None

    @staticmethod
    def has_auth_cookies(context: Any) -> bool:
        """Check whether the browser context holds valid Google authentication cookies.

        Args:
            context: Playwright BrowserContext instance.

        Returns:
            True when at least one non-expired Google auth cookie is present.
        """
        try:
            cookies = context.cookies()
            now_ts = time.time()
            return any(_is_valid_auth_cookie(cookie, now_ts) for cookie in cookies)
        except Exception as exc:
            logger.warning("Error inspecting browser context cookies: %s", exc)
            return False

    @staticmethod
    def is_page_signed_in(page: Any) -> bool:
        """Inspect page URL and DOM to confirm an authenticated Gemini session.

        Args:
            page: Playwright Page instance.

        Returns:
            True when on `gemini.google.com` with an account avatar and no Sign-in link
            (note-studio ISSUE-025).
        """
        try:
            url = page.url or ""
            if "gemini.google.com" not in url or "accounts.google.com" in url:
                return False
            sign_in_sel = (
                'a[href*="accounts.google.com/ServiceLogin"], '
                'a[aria-label*="Sign in"], '
                'a[aria-label*="登入"], '
                'button:has-text("Sign in"), '
                'a:has-text("Sign in"), '
                'a:has-text("登入")'
            )
            if page.query_selector(sign_in_sel) is not None:
                return False
            avatar_sel = (
                'a[href*="accounts.google.com/SignOutOptions"], '
                'a[aria-label*="Google Account"], '
                'a[aria-label*="Google 帳戶"], '
                'button[aria-label*="Google Account"], '
                'button[aria-label*="Google 帳戶"]'
            )
            return page.query_selector(avatar_sel) is not None
        except Exception as exc:
            logger.warning("is_page_signed_in: cannot inspect page; treating as signed out: %s", exc)
            return False

    def confirm_signed_in(self, port: int, storage_state_path: Path) -> bool:
        """Attach briefly via CDP, confirm Gemini sign-in, and save `storage_state.json`.

        Args:
            port: Local Chrome debugging port.
            storage_state_path: File path to save Playwright storage state.

        Returns:
            True if sign-in was confirmed and saved; False otherwise.
        """
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(chrome_session.cdp_endpoint(port))
            try:
                context = browser.contexts[0]
                pages = [pg for pg in context.pages if not pg.is_closed()]
                if not (self.has_auth_cookies(context) and any(self.is_page_signed_in(pg) for pg in pages)):
                    return False
                ensure_private_dir(storage_state_path.parent)
                context.storage_state(path=str(storage_state_path))
                os.chmod(storage_state_path, 0o600)
                logger.info("Verified Gemini sign-in; storage state saved to %s", storage_state_path)
                chrome_session.quit_chrome(browser)
                return True
            finally:
                try:
                    browser.close()
                except Exception as exc:
                    logger.info("confirm_signed_in: Chrome already gone on disconnect: %s", exc)

    def _try_confirm_gemini_tab(self, port: int, urls: list[str], storage_state_path: Path) -> bool:
        """Wait briefly for Gemini avatar rendering once a tab reaches Gemini, then confirm sign-in.

        Args:
            port: Chrome debugging port.
            urls: Current open tab URLs.
            storage_state_path: Destination `storage_state.json` path.

        Returns:
            True if signed in and saved.
        """
        if not any(u.startswith("https://gemini.google.com/") for u in urls):
            return False
        time.sleep(2.0)
        try:
            return self.confirm_signed_in(port, storage_state_path)
        except Exception as exc:
            logger.warning("Sign-in confirmation failed, will retry: %s", exc)
            return False

    def wait_for_login_completion(self, port: int, storage_state_path: Path, timeout_seconds: int) -> bool:
        """Poll tab URLs until sign-in completes, Chrome closes, or timeout elapses.

        Args:
            port: Chrome debugging port.
            storage_state_path: Destination `storage_state.json` path.
            timeout_seconds: Maximum wait seconds.

        Returns:
            True when sign-in was confirmed and persisted.
        """
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                urls = chrome_session.list_tab_urls(port)
            except OSError as exc:
                logger.info("Chrome closed by user before sign-in was confirmed: %s", exc)
                return False
            if self._try_confirm_gemini_tab(port, urls, storage_state_path):
                return True
            time.sleep(1.0)
        logger.warning("Timed out after %ds waiting for Google sign-in", timeout_seconds)
        return False

    def run_browser_login(self, storage_state_path: Path, timeout_seconds: int) -> None:
        """Open real Google Chrome on the Gemini login URL and wait for sign-in completion.

        Args:
            storage_state_path: Destination `storage_state.json` path.
            timeout_seconds: Maximum wait seconds.
        """
        ensure_private_dir(self.profile_dir)
        launch = chrome_session.ChromeLaunch(
            chrome_path=self.chrome_path,
            user_data_dir=self.chrome_user_data_dir(),
            start_url=chrome_session.LOGIN_URL,
        )
        already_running = chrome_session.running_port(launch.user_data_dir) is not None
        port = chrome_session.ensure_chrome(launch)
        if already_running:
            chrome_session.open_tab(port, chrome_session.LOGIN_URL)
        logger.info("Chrome window opened on port %d, waiting for user login...", port)
        self.wait_for_login_completion(port, storage_state_path, timeout_seconds)

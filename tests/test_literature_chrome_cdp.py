"""SPEC-022 part 2: the literature browser runs real Chrome on its own profile and attaches over CDP."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from notebooklm_batch_studio.adapters.literature import browser as browser_mod
from notebooklm_batch_studio.adapters.literature.browser import BrowserPublisherFetcher

logger = logging.getLogger(__name__)


class LiteratureChromeTest(unittest.TestCase):
    """Chrome is started normally (not by Playwright), reused through CDP, and closed on exit."""

    def setUp(self) -> None:
        """Create a temporary profile folder and fake Playwright / Chrome helpers."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.profile = Path(self.tmpdir.name) / "literature_browser"
        self.pw = mock.MagicMock()
        self.browser = self.pw.chromium.connect_over_cdp.return_value
        self.context = self.browser.contexts[0]
        starter = mock.MagicMock()
        starter.return_value.start.return_value = self.pw
        self.patches = [
            mock.patch.object(browser_mod, "sync_playwright", starter),
            mock.patch.object(browser_mod.chrome_session, "ensure_chrome", return_value=9222),
            mock.patch.object(browser_mod.chrome_session, "quit_chrome"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        """Stop patches and remove temporary files."""
        for p in self.patches:
            p.stop()
        self.tmpdir.cleanup()

    def test_starts_real_chrome_on_existing_profile_and_attaches(self) -> None:
        """`ensure_chrome` launches Chrome on the same profile folder; Playwright only attaches."""
        fetcher = BrowserPublisherFetcher(self.profile, "", ("", ""), 0)
        fetcher.chrome_path = "/chrome"
        with fetcher:
            launch = browser_mod.chrome_session.ensure_chrome.call_args.args[0]  # type: ignore[attr-defined]
            self.assertEqual((launch.chrome_path, launch.user_data_dir), ("/chrome", self.profile))
            self.assertFalse(launch.headless)
            self.pw.chromium.connect_over_cdp.assert_called_once_with("http://127.0.0.1:9222")
            self.pw.chromium.launch_persistent_context.assert_not_called()
            self.assertIs(fetcher.new_page(), self.context.new_page.return_value)
        browser_mod.chrome_session.quit_chrome.assert_called_once_with(self.browser)  # type: ignore[attr-defined]
        self.pw.stop.assert_called_once()

    def test_bot_check_unattended_raises_without_clicking(self) -> None:
        """With wait 0 a Cloudflare page raises NeedsUserError; nothing is clicked or typed."""
        fetcher = BrowserPublisherFetcher(self.profile, "", ("", ""), 0)
        page = mock.MagicMock(url="https://example.org/article")
        page.title.return_value = "Just a moment..."
        clock = iter(range(0, 1000, 5))
        with mock.patch.object(browser_mod.time, "monotonic", side_effect=lambda: next(clock)):
            with self.assertRaises(browser_mod.NeedsUserError):
                fetcher.settle(page)
        page.click.assert_not_called()
        page.fill.assert_not_called()


if __name__ == "__main__":
    unittest.main()

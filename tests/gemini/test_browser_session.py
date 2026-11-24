"""單元測試：瀏覽器會話管理器生命週期與視窗等待保護 (note-studio ISSUE-050)。

驗證 BrowserSessionManager 在 auto_close=True 下能安全關閉分頁而不阻塞背景 Worker，
並確認 _wait_window_closed 具備超時與斷線跳脫機制。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from notebooklm_batch_studio.adapters.gemini.browser_session import BrowserSessionManager


class TestBrowserSessionManager(unittest.TestCase):
    """驗證瀏覽器會話生命週期管理與避免死鎖機制。"""

    def setUp(self) -> None:
        """建立臨時測試目錄。"""
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        self.mgr = BrowserSessionManager(data_dir=self.data_dir)

    def tearDown(self) -> None:
        """清理臨時測試目錄。"""
        self.tmp.cleanup()

    def test_wait_window_closed_breaks_when_page_already_closed(self) -> None:
        """當頁面已關閉時，_wait_window_closed 應立即跳出而不等待。"""
        page = MagicMock()
        page.is_closed.return_value = True
        self.mgr._wait_window_closed(page, max_wait_seconds=10)
        page.wait_for_timeout.assert_not_called()

    def test_wait_window_closed_breaks_on_page_exception(self) -> None:
        """當頁面連線斷開或拋出異常時，_wait_window_closed 應安全跳出。"""
        page = MagicMock()
        page.is_closed.return_value = False
        page.wait_for_timeout.side_effect = RuntimeError("Target closed")
        self.mgr._wait_window_closed(page, max_wait_seconds=10)
        page.wait_for_timeout.assert_called_once()

    def test_open_driver_with_auto_close_releases_without_waiting(self) -> None:
        """auto_close=True 時，退出 context 應直接呼叫 _release，不進入等待迴圈。"""
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_context.pages = [mock_page]
        mock_page.is_closed.return_value = False

        ret = (mock_browser, mock_context, mock_page)
        with (
            patch("playwright.sync_api.sync_playwright") as mock_playwright,
            patch.object(self.mgr, "_create_browser_and_page", return_value=ret),
            patch.object(self.mgr, "_sync_storage_state"),
            patch.object(self.mgr, "_wait_window_closed") as mock_wait,
            patch("notebooklm_batch_studio.adapters.gemini.web_driver.GeminiWebDriver"),
        ):
            mock_playwright.return_value.__enter__.return_value = mock_p

            with self.mgr.open_driver(headless=False, auto_close=True) as driver:
                self.assertIsNotNone(driver)

            mock_wait.assert_not_called()
            mock_page.close.assert_called_once()

    def test_open_driver_error_in_window_mode_waits_only_once(self) -> None:
        """An error in window mode keeps the window open for one wait, not two (120 s + 180 s)."""
        ret = (MagicMock(), MagicMock(), MagicMock())
        with (
            patch("playwright.sync_api.sync_playwright"),
            patch.object(self.mgr, "_create_browser_and_page", return_value=ret),
            patch.object(self.mgr, "_sync_storage_state"),
            patch.object(self.mgr, "_wait_window_closed") as mock_wait,
            patch("notebooklm_batch_studio.adapters.gemini.web_driver.GeminiWebDriver"),
        ):
            with self.assertRaises(RuntimeError):
                with self.mgr.open_driver(headless=False, auto_close=False):
                    raise RuntimeError("generation failed")

            self.assertEqual(mock_wait.call_count, 1)


if __name__ == "__main__":
    unittest.main()

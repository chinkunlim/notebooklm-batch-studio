"""Gemini 網頁自動化適配器單元測試（note-studio SPEC-012, Plan §9）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from notebooklm_batch_studio.adapters.gemini.browser_session import BrowserSessionManager
from notebooklm_batch_studio.adapters.gemini.selectors import GEMINI_SELECTORS
from notebooklm_batch_studio.adapters.gemini.web_driver import (
    GeminiQuotaExceededError,
    GeminiWebDriver,
)


class GeminiAdapterTest(unittest.TestCase):
    """測試 Gemini 網頁自動化適配器元件與例外處理。"""

    def test_selectors_completeness(self) -> None:
        """確認 DOM 元素選取器集中表涵蓋關鍵互動元件。"""
        self.assertIn("new_chat_button", GEMINI_SELECTORS)
        self.assertIn("prompt_textarea", GEMINI_SELECTORS)
        self.assertIn("send_button", GEMINI_SELECTORS)
        self.assertIn("copy_button", GEMINI_SELECTORS)
        self.assertIn("file_upload_input", GEMINI_SELECTORS)
        self.assertIn("quota_warning_banner", GEMINI_SELECTORS)

    def test_browser_session_profile_in_data_dir(self) -> None:
        """持久化瀏覽器 Profile 必須位於 DATA_DIR 內。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_data_dir = Path(temp_dir)
            session_mgr = BrowserSessionManager(data_dir=fake_data_dir)
            profile_dir = session_mgr.get_profile_dir()

            self.assertTrue(profile_dir.is_relative_to(fake_data_dir))
            self.assertEqual(profile_dir, fake_data_dir / "state" / "gemini_profile")

    def test_web_driver_detects_quota_limit(self) -> None:
        """當網頁出現 Quota 限制警示時，正確拋出 GeminiQuotaExceededError (Refs: note-studio ISSUE-043)。"""
        mock_page = MagicMock()
        mock_banner = MagicMock()
        mock_banner.count.return_value = 2
        mock_banner.first.is_visible.return_value = True
        mock_page.locator.return_value = mock_banner

        driver = GeminiWebDriver(page=mock_page)
        self.assertTrue(driver.check_quota_exceeded())

        with self.assertRaises(GeminiQuotaExceededError):
            driver.assert_quota_available()

    def test_quota_warning_banner_selector_includes_limit_reached(self) -> None:
        """驗證 Quota 限流選擇器包含英文 Limit reached 模式 (Refs: note-studio ISSUE-043)。"""
        from notebooklm_batch_studio.adapters.gemini.selectors import GEMINI_SELECTORS

        selector = GEMINI_SELECTORS.get("quota_warning_banner", "")
        self.assertIn(':has-text("Limit reached")', selector)
        self.assertIn(':has-text("已達上限")', selector)

    def test_web_driver_extract_raw_markdown_via_copy(self) -> None:
        """透過點擊最後則回覆的複製按鈕取得原始 Markdown。"""
        mock_page = MagicMock()
        mock_copy_btn = MagicMock()
        mock_copy_btn.count.return_value = 1
        mock_copy_btn.last = mock_copy_btn

        mock_empty = MagicMock()
        mock_empty.count.return_value = 0
        mock_empty.first.is_visible.return_value = False

        mock_resp_container = MagicMock()
        mock_resp_container.count.return_value = 1
        mock_resp_container.last = mock_resp_container
        mock_resp_container.locator.return_value = mock_copy_btn

        def locator_dispatch(sel: str) -> MagicMock:
            if "response" in sel.lower():
                return mock_resp_container
            if "copy" in sel.lower():
                return mock_copy_btn
            return mock_empty

        mock_page.locator.side_effect = locator_dispatch
        # 模擬剪貼簿內容
        mock_page.evaluate.return_value = "## 概覽\n- 極限 (p.1)\n<!-- END -->"

        driver = GeminiWebDriver(page=mock_page)
        content = driver.get_last_response_markdown()

        self.assertIn("## 概覽", content)
        self.assertIn("<!-- END -->", content)
        mock_copy_btn.click.assert_called_once()

    def test_send_prompt_records_previous_response_and_waits_for_new(self) -> None:
        """送出 prompt 後若立刻複製到上一輪回覆，必須繼續等待直到新回覆產生 (Refs: note-studio ISSUE-054)。"""
        mock_page = MagicMock()
        mock_copy_btn = MagicMock()
        mock_copy_btn.count.return_value = 1
        mock_copy_btn.last = mock_copy_btn

        mock_generating = MagicMock()
        mock_generating.count.return_value = 0
        mock_generating.first.is_visible.return_value = False

        mock_resp_container = MagicMock()
        resp_count = 1
        mock_resp_container.count.side_effect = lambda: resp_count
        mock_resp_container.last = mock_resp_container
        mock_resp_container.locator.return_value = mock_copy_btn

        def locator_side_effect(selector: str) -> MagicMock:
            if "response" in selector.lower():
                return mock_resp_container
            if "copy" in selector.lower():
                return mock_copy_btn
            return mock_generating

        mock_page.locator.side_effect = locator_side_effect

        old_response = "## 模組四：【康乃爾高頻考點筆記】\n舊回覆內容超過十五個字元..."
        new_response = "## 模組六：【費曼概念精講】\n新回覆內容超過十五個字元..."

        driver = GeminiWebDriver(page=mock_page)

        # 模擬在 send_prompt 前，剪貼簿已有上一輪回覆
        mock_page.evaluate.return_value = old_response

        # 發送新 prompt
        driver.send_prompt("請生成第六模組費曼筆記")
        # 提示詞發送後，新回覆容器於 DOM 中增加 (Refs: note-studio ISSUE-061)
        resp_count = 2

        # 模擬：第一次呼叫 _copy_via_button (剛發送 prompt 時) 拿到 old_response
        # 第二次呼叫時才拿到 new_response
        call_count = 0

        def evaluate_side_effect(script: str) -> str | None:
            nonlocal call_count
            if "readText" in script:
                call_count += 1
                if call_count == 1:
                    return old_response
                return new_response
            return None

        mock_page.evaluate.side_effect = evaluate_side_effect

        content = driver.get_last_response_markdown(timeout_seconds=5)
        self.assertEqual(content, new_response)

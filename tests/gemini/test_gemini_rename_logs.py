"""Gemini chat rename must log WARNING on failure (ported from note-studio ISSUE-034).

Only the web-driver part is ported; note-studio's chat_renamer service and HTTP endpoints were
not brought into this project.
"""

from __future__ import annotations

import unittest


class TestRenameWarningLogs(unittest.TestCase):
    """驗證改名失敗必定記錄 WARNING log，嚴禁吞沒式靜默失敗（note-studio ISSUE-034）。"""

    def test_rename_failure_emits_warning_log(self) -> None:
        """當 DOM 元素找不到時，rename_current_chat 必須輸出 WARNING 級別 log 說明哪個元素缺失。"""
        from unittest.mock import MagicMock

        from notebooklm_batch_studio.adapters.gemini.web_driver import GeminiWebDriver

        fake_page = MagicMock()
        fake_locator = MagicMock()
        fake_locator.count.return_value = 0
        fake_locator.is_visible.return_value = False
        fake_locator.first = fake_locator
        fake_page.locator.return_value = fake_locator

        driver = GeminiWebDriver.__new__(GeminiWebDriver)
        driver.page = fake_page
        driver.selectors = {
            "chat_title_menu": "[data-test-id='menu']",
            "rename_chat_item": "[data-test-id='rename']",
            "chat_title_input": "input[name='title']",
            "rename_confirm_button": "button[type='submit']",
        }
        driver._desired_chat_title = ""

        with self.assertLogs("notebooklm_batch_studio.adapters.gemini.web_driver", level="WARNING") as cm:
            result = driver.rename_current_chat("Test Title")

        self.assertFalse(result)
        self.assertTrue(
            any("WARNING" in line and "menu" in line.lower() for line in cm.output),
            f"Expected WARNING log mentioning missing menu button, got: {cm.output}",
        )

    def test_rename_exception_emits_warning_not_debug(self) -> None:
        """當改名過程發生未預期異常時，必須以 WARNING 輸出，嚴禁以 debug 隱匿（note-studio ISSUE-034）。"""
        from unittest.mock import MagicMock

        from notebooklm_batch_studio.adapters.gemini.web_driver import GeminiWebDriver

        fake_page = MagicMock()
        fake_page.locator.side_effect = RuntimeError("DOM disconnected")

        driver = GeminiWebDriver.__new__(GeminiWebDriver)
        driver.page = fake_page
        driver.selectors = {
            "chat_title_menu": "[data-test-id='menu']",
            "rename_chat_item": "[data-test-id='rename']",
            "chat_title_input": "input[name='title']",
            "rename_confirm_button": "button[type='submit']",
        }
        driver._desired_chat_title = ""

        with self.assertLogs("notebooklm_batch_studio.adapters.gemini.web_driver", level="WARNING") as cm:
            result = driver.rename_current_chat("Test Title")

        self.assertFalse(result)
        self.assertTrue(
            any("WARNING" in line and "DOM disconnected" in line for line in cm.output),
            f"Expected WARNING log mentioning exception, got: {cm.output}",
        )


if __name__ == "__main__":
    unittest.main()

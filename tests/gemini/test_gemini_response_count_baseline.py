"""Gemini WebDriver 基於回覆數量之新回應判定測試（note-studio ISSUE-061）。

驗證 send_prompt 記下當前回覆數量，當新回覆尚未在 DOM 中產生時，
無論是 _copy_via_button 或 _read_response_fallback 均不得回傳上一則舊回覆。
"""

from __future__ import annotations

import unittest

from playwright.sync_api import sync_playwright

from notebooklm_batch_studio.adapters.gemini.web_driver import GeminiWebDriver


class GeminiResponseCountBaselineTest(unittest.TestCase):
    """測試送出提示詞後基於回覆數量之新回應判定與隔離。"""

    def test_dom_fallback_does_not_return_previous_response_before_new_appears(self) -> None:
        """送出後新回覆尚未出現時，DOM 讀取不可回傳上一則 (note-studio ISSUE-061)。"""
        html_fixture = """
        <!DOCTYPE html>
        <html>
        <head><title>Gemini Turn Test</title></head>
        <body>
          <div class="chat-container">
            <model-response id="resp-1">
              <div class="content">舊回覆：模組一【心智圖與章節架構】完整論述內容超過十五字元</div>
              <button aria-label="複製" id="btn-copy-1">複製</button>
            </model-response>
          </div>
          <rich-textarea>
            <div class="ql-editor" contenteditable="true"></div>
          </rich-textarea>
          <button aria-label="傳送" id="btn-send">傳送</button>
        </body>
        </html>
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html_fixture)

            driver = GeminiWebDriver(page=page)

            # 1. 送出新提示詞
            driver.send_prompt("請生成模組二：詳細大綱")

            # 2. 新回覆尚未在 DOM 出現：此時 count 為 1（仍等於 baseline）
            # 驗證 DOM 備援不可抓取上一則舊回覆
            fallback_text = driver._read_response_fallback()
            self.assertIsNone(
                fallback_text,
                f"新回覆尚未出現時，DOM 備援不可回傳舊回覆，但回傳了: {fallback_text}",
            )

            # 驗證 複製按鈕 亦不可點擊上一則舊回覆
            copy_text = driver._copy_via_button()
            self.assertIsNone(
                copy_text,
                f"新回覆尚未出現時，複製按鈕不可複製舊回覆，但回傳了: {copy_text}",
            )

            # 3. 模擬新回覆出現在 DOM（count 變為 2 > baseline 1）
            page.evaluate("""() => {
                const container = document.querySelector('.chat-container');
                const newResp = document.createElement('model-response');
                newResp.id = 'resp-2';
                newResp.innerHTML = `
                    <div class="content">新回覆：模組二【詳細大綱 Outline】完整論述內容超過十五字元</div>
                    <button aria-label="複製" id="btn-copy-2">複製</button>
                `;
                container.appendChild(newResp);
            }""")

            # 4. 新回覆出現後，DOM 備援與複製皆能正確取得第二則新回覆
            new_fallback = driver._read_response_fallback()
            self.assertIsNotNone(new_fallback)
            self.assertIn("模組二【詳細大綱 Outline】", new_fallback or "")
            self.assertNotIn("模組一", new_fallback or "")

            browser.close()

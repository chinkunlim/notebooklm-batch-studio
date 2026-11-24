"""Gemini WebDriver 複製按鈕選取器測試（ported from note-studio ISSUE-058）。

The StepValidator DOM-fallback case is not ported: this project validates steps with
`validate_step_output`, which has no block-type expectations.

驗證複製按鈕只在最後一則模型回覆容器內尋找，排除側邊欄含有「複製」字樣之對話項目。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

from notebooklm_batch_studio.adapters.gemini.web_driver import GeminiWebDriver


class GeminiCopySelectorTest(unittest.TestCase):
    """測試複製按鈕定位範圍與側邊欄對話隔離。"""

    def test_copy_button_ignores_sidebar_conversation(self) -> None:
        """側邊欄對話名稱含「複製」時，不得被誤認為模型回覆之複製按鈕 (note-studio ISSUE-058)。"""
        html_fixture = """
        <!DOCTYPE html>
        <html>
        <head><title>Gemini Mock</title></head>
        <body>
          <div class="chat-container">
            <model-response id="resp-1">
              <div class="content">第一則回覆</div>
              <button aria-label="複製" id="btn-copy-resp-1">複製</button>
            </model-response>
            <model-response id="resp-2">
              <div class="content">這是第二則回覆（最後一則）</div>
              <button aria-label="複製" id="btn-copy-target">複製</button>
            </model-response>
          </div>
          <nav class="sidebar-chats">
            <div class="chat-item">
              <a aria-label="複製BART實驗求助信撰寫">複製BART實驗求助信撰寫</a>
              <button aria-label="More options for 複製BART實驗求助信撰寫" id="btn-sidebar-trap">選單</button>
            </div>
          </nav>
        </body>
        </html>
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html_fixture)

            # 注入點擊記錄與剪貼簿模擬
            page.evaluate("""() => {
                window.__clickedId = null;
                document.querySelectorAll('button').forEach(btn => {
                    btn.addEventListener('click', () => {
                        window.__clickedId = btn.id;
                    });
                });
                navigator.clipboard = {
                    readText: async () => "## 模擬複製文字內容 (長度超過十五字元)"
                };
            }""")

            driver = GeminiWebDriver(page=page)
            res = driver._copy_via_button()

            clicked_id = page.evaluate("() => window.__clickedId")
            browser.close()

            # 必須點擊最後一則回覆內的複製按鈕，絕不可點擊側邊欄 trap
            self.assertEqual(
                clicked_id,
                "btn-copy-target",
                f"點擊了錯誤的按鈕: {clicked_id}（側邊欄干擾）",
            )
            self.assertIsNotNone(res)
            self.assertIn("模擬複製文字", res or "")

    def test_copy_falls_back_to_markdown_code_block_copy_button(self) -> None:
        """當動作列複製按鈕不存在時，應優先點擊回覆內 Markdown 程式碼區塊的複製按鈕。"""
        html_fixture = """
        <!DOCTYPE html>
        <html>
        <head><title>Gemini Mock</title></head>
        <body>
          <div class="chat-container">
            <model-response id="resp-target">
              <div class="model-response-text">
                <div class="code-block" data-language="markdown">
                  <div class="code-header">
                    <span>Markdown</span>
                    <button aria-label="Copy code" id="btn-copy-code-block">複製程式碼</button>
                  </div>
                  <pre><code># 核心筆記內容</code></pre>
                </div>
              </div>
              <div class="message-actions">
                <button aria-label="Good response">讚</button>
                <button aria-label="Bad response">倒讚</button>
                <!-- 故意沒有動作列複製按鈕 -->
              </div>
            </model-response>
          </div>
        </body>
        </html>
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html_fixture)

            page.evaluate("""() => {
                window.__clickedId = null;
                document.querySelectorAll('button').forEach(btn => {
                    btn.addEventListener('click', () => {
                        window.__clickedId = btn.id;
                    });
                });
                navigator.clipboard = {
                    readText: async () => "## 來自程式碼區塊複製按鈕之原始 Markdown 內容 (長度超過十五字元)"
                };
            }""")

            driver = GeminiWebDriver(page=page)
            res = driver._copy_via_button()
            clicked_id = page.evaluate("() => window.__clickedId")
            browser.close()

            self.assertEqual(
                clicked_id,
                "btn-copy-code-block",
                f"未成功點擊程式碼區塊複製按鈕: {clicked_id}",
            )
            self.assertIsNotNone(res)
            self.assertIn("來自程式碼區塊", res or "")

    def test_dom_fallback_dumps_diagnostic_html(self) -> None:
        """當無任何複製按鈕可用退回 DOM 讀取時，driver 必須寫入診斷檔並標記 was_dom_fallback。"""
        html_fixture = """
        <!DOCTYPE html>
        <html>
        <head><title>Gemini Mock</title></head>
        <body>
          <div class="chat-container">
            <model-response id="resp-target">
              <div class="model-response-text">
                <p>這是僅有純文字渲染的最後一則回覆內容，超過十五個字元。</p>
              </div>
            </model-response>
          </div>
        </body>
        </html>
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            diag_dir = Path(tmp_dir) / "logs"
            diag_dir.mkdir(parents=True, exist_ok=True)

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(html_fixture)

                driver = GeminiWebDriver(page=page, diagnostic_dir=diag_dir)
                fallback_text = driver._read_response_fallback()
                browser.close()

                self.assertIsNotNone(fallback_text)
                self.assertTrue(driver.was_dom_fallback)

                dump_files = list(diag_dir.glob("dom_fallback_*.html"))
                self.assertGreater(len(dump_files), 0, "未寫入 DOM fallback 診斷檔")
                content = dump_files[0].read_text(encoding="utf-8")
                self.assertIn("這是僅有純文字渲染的最後一則回覆內容", content)

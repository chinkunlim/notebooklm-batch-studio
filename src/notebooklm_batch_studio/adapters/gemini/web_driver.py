"""Gemini 網頁自動化操作驅動器（note-studio SPEC-012, Plan §9.3）。

透過 Playwright 操作 Gemini 網頁前端：
1. 開啟新 Chat 並命名章節標題
2. 上傳章節課本 PDF 與動態規格 Markdown
3. 送出逐步生成之 Prompt
4. 點擊「複製」按鈕精確獲取未被 DOM 破壞的原始 Markdown
5. 監控 Quota 狀態與異常處置
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.gemini import chat_actions, model_controls, response_reader
from notebooklm_batch_studio.adapters.gemini.selectors import GEMINI_SELECTORS, is_model_match
from notebooklm_batch_studio.domain.note_pipeline import ModelMismatchError, QuotaExceededError

logger = logging.getLogger(__name__)


class GeminiAutomationError(Exception):
    """Gemini 網頁自動化通用異常。"""


class GeminiQuotaExceededError(GeminiAutomationError, QuotaExceededError):
    """Gemini 配額用盡或遭限流異常。"""


GeminiModelMismatchError = ModelMismatchError


class GeminiWebDriver:
    """Gemini 網頁操作驅動器。"""

    def __init__(
        self,
        page: Any,
        selectors: dict[str, str] | None = None,
        diagnostic_dir: Path | None = None,
    ) -> None:
        """初始化驅動器。

        Args:
            page: Playwright Page 物件。
            selectors: 自訂 DOM 選取器（若為 None 則採用 GEMINI_SELECTORS）。
            diagnostic_dir: 診斷檔案儲存目錄（若為 None 則停用 DOM 診斷傾印）。
        """
        self.page = page
        self.selectors = selectors or GEMINI_SELECTORS
        self.diagnostic_dir: Path | None = diagnostic_dir
        self.was_dom_fallback: bool = False
        self.last_read_source: str = "button"
        self._last_sent_prompt: str = ""
        self._desired_chat_title: str = ""
        self._baseline_response_text: str | None = None
        self._baseline_response_count: int = 0
        logger.debug("GeminiWebDriver initialized")

    def _pause(self, ms: int, where: str, sleep_fallback: bool = False) -> None:
        """在頁面上等待；失敗（頁面已關閉等）時記 WARNING，必要時改用 time.sleep 補足等待（R100）。

        Args:
            ms: 等待毫秒數。
            where: 呼叫端名稱（寫進 log）。
            sleep_fallback: 頁面等待失敗時是否改用 time.sleep 等同樣時間。
        """
        try:
            self.page.wait_for_timeout(ms)
        except Exception as exc:
            logger.warning("%s: wait on the page failed (page closed?): %s", where, exc)
            if sleep_fallback:
                time.sleep(ms / 1000)

    def close_tab(self) -> None:
        """關閉這個 driver 使用的分頁（自動重試換新分頁前、或多工章節結束後呼叫，note-studio ADR-016）。

        分頁已關或瀏覽器已斷線時只記 log，不拋出。
        """
        try:
            if not self.page.is_closed():
                self.page.close()
                logger.info("Closed the Gemini tab")
        except Exception as exc:
            logger.warning("close_tab: could not close the Gemini tab: %s", exc)

    def start_new_chat(self, chat_title: str = "") -> None:
        """點擊建立新對話按鈕，準備發送提示詞。

        Args:
            chat_title: 對話標題說明（供日後追蹤）。
        """
        self._desired_chat_title = chat_title
        self._last_sent_prompt = ""
        self._baseline_response_text = None
        new_chat_sel = self.selectors.get("new_chat_button", "")
        if not new_chat_sel:
            return
        try:
            btn = self.page.locator(new_chat_sel).first
            if btn.count() > 0 and btn.is_visible():
                btn.click()
                self._pause(1500, "start_new_chat")
                logger.info("Clicked new chat button for chat: %s", chat_title)
        except Exception as exc:
            logger.warning("Failed to click new chat button: %s", exc)

    def _find_rename_menu_button(self, menu_sel: str) -> Any:
        """尋找對話選單觸發按鈕。

        Args:
            menu_sel: 選單按鈕 CSS 選擇器。

        Returns:
            Playwright Locator 實體（若找到可見元素），否則為 None。
        """
        return chat_actions.find_rename_menu_button(self, menu_sel)

    def _submit_rename_input(self, target_title: str, input_sel: str, save_sel: str) -> bool:
        """在重命名輸入框填入新標題並送出確認。

        Args:
            target_title: 欲設定之新標題。
            input_sel: 輸入框選擇器。
            save_sel: 確認按鈕選擇器。

        Returns:
            若輸入框成功填寫並送出回傳 True，否則為 False。
        """
        return chat_actions.submit_rename_input(self, target_title, input_sel, save_sel)

    def rename_current_chat(self, new_title: str = "") -> bool:
        """嘗試在 Gemini 網頁前端側邊欄將當前對話重命名為指定標題。

        Args:
            new_title: 欲設定之新標題（若為空則採用 start_new_chat 時暫存之標題）。

        Returns:
            若成功重命名回傳 True，否則為 False。
        """
        return chat_actions.rename_current_chat(self, new_title)

    def select_model(self, model_name: str, thinking_level: str = "") -> None:
        """嘗試在 Gemini 網頁前端選單切換至指定的 AI 模型與思考深度。

        Args:
            model_name: 目標模型關鍵字（如 '3.1 Pro'、'3.8 Flash'）。
            thinking_level: 思考深度關鍵字（如 'Medium'、'High'、'Low'）。
        """
        model_controls.select_model(self, model_name, thinking_level)

    def get_current_model_menu_text(self) -> str:
        """讀取輸入框旁模型選擇器按鈕目前顯示之文字或標籤。

        Returns:
            模型按鈕文字或標籤（若找不到回傳空字串）。
        """
        return model_controls.get_current_model_menu_text(self.page, self.selectors)

    def verify_pre_send_model(self, target_model: str, thinking_level: str = "") -> None:
        """送出提示詞前檢查模型選單，不符時嘗試重新選擇一次；仍不符則拋出異常中斷送出。

        Args:
            target_model: 預期之模型名稱。
            thinking_level: 思考深度關鍵字。

        Raises:
            GeminiModelMismatchError: 模型仍不符時。
        """
        if not target_model:
            return
        curr = self.get_current_model_menu_text()
        if curr and is_model_match(target_model, curr):
            return
        logger.warning(
            "Pre-send model '%s' does not match target '%s'; reselecting...",
            curr,
            target_model,
        )
        self.select_model(target_model, thinking_level=thinking_level)
        curr_after = self.get_current_model_menu_text()
        if curr_after and not is_model_match(target_model, curr_after):
            msg = f"模型選單文字為 '{curr_after}'，與要求模型 '{target_model}' 不符"
            raise GeminiModelMismatchError(msg, detected_model=curr_after)

    def open_chat(self, chat_url: str) -> None:
        """開啟指定的 Gemini 對話網址（只讀導航）。

        Args:
            chat_url: 對話網址。
        """
        self.page.goto(chat_url, timeout=30000)
        self._pause(1000, "open_chat")

    def _read_model_from_scope(self, scope: Any) -> str:
        """點擊指定回覆範圍內之「⋯」選單並讀取 response details 之模型名稱。

        Args:
            scope: 回覆節點 locator。

        Returns:
            偵測到的模型名稱字串（失敗回傳 'unknown'）。
        """
        return model_controls.read_model_from_scope(self, scope)

    def get_last_response_model(self) -> str:
        """點擊最後一則回覆之「⋯」選單並讀取 response details 之「Used ...」模型名稱。

        Returns:
            偵測到的模型名稱字串（若讀取失敗記 warning 並回傳 'unknown'）。
        """
        resp_sel = self.selectors.get("response_container", "")
        target_scope = self.page
        if resp_sel:
            responses = self.page.locator(resp_sel)
            if responses.count() <= self._baseline_response_count:
                logger.warning("get_last_response_model: response count not increased")
                return "unknown"
            target_scope = responses.last
        return self._read_model_from_scope(target_scope)

    def get_all_response_models(self) -> list[str]:
        """遍歷對話中所有回覆之 response details 中的模型名稱。

        Returns:
            各則回覆偵測到之模型名稱清單。
        """
        resp_sel = self.selectors.get("response_container", "")
        if not resp_sel:
            return []
        responses = self.page.locator(resp_sel)
        count = responses.count()
        logger.info("get_all_response_models: found %d responses to inspect", count)
        return [self._read_model_from_scope(responses.nth(i)) for i in range(count)]

    def check_quota_exceeded(self) -> bool:
        """檢查頁面上是否出現配額上限警示 (Refs: note-studio ISSUE-043)。

        Returns:
            若已達到配額上限則為 True，否則為 False。
        """
        selector = self.selectors.get("quota_warning_banner", "")
        if not selector:
            return False
        try:
            banner = self.page.locator(selector)
            return bool(banner.count() > 0 and banner.first.is_visible())
        except Exception as exc:
            logger.warning("Quota check encountered error: %s", exc)
            return False

    def get_quota_notice_text(self) -> str | None:
        """獲取頁面上限流或配額提示之原始文字 (note-studio ISSUE-065)。

        Returns:
            若找到警示橫幅則回傳其文字內容，否則為 None。
        """
        selector = self.selectors.get("quota_warning_banner", "")
        if not selector:
            return None
        try:
            banner = self.page.locator(selector)
            if banner.count() > 0 and banner.first.is_visible():
                raw = banner.first.inner_text()
                if not isinstance(raw, str):
                    raw = banner.first.text_content()
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
        except Exception as exc:
            logger.warning("Failed to extract quota notice text: %s", exc)
        return None

    def assert_quota_available(self) -> None:
        """確認配額可用；若超限則解析恢復時間並拋出異常 (note-studio ISSUE-065)。

        Raises:
            GeminiQuotaExceededError: 當頁面出現限流警告時。
        """
        if self.check_quota_exceeded():
            notice_text = self.get_quota_notice_text()
            logger.warning("Gemini quota notice raw text: %s", notice_text)
            from notebooklm_batch_studio.domain.quota_parser import parse_quota_resume_time

            resume_dt = parse_quota_resume_time(notice_text or "")
            raise GeminiQuotaExceededError(
                f"Gemini 配額已用盡或遭到限流: {notice_text or '未取得提示文字'}",
                raw_text=notice_text,
                resume_after=resume_dt,
            )

    def refresh_and_check_quota(self) -> bool:
        """重新整理瀏覽器頁面並檢驗 Quota 是否已恢復 (note-studio SPEC-019)。

        Returns:
            若重新整理後警告橫幅已消失（Quota 可用）則回傳 True，否則為 False。
        """
        try:
            logger.info("Refreshing Gemini web driver page to re-verify quota availability...")
            self.page.reload()
            self.page.wait_for_timeout(2000)
            available = not self.check_quota_exceeded()
            if available:
                logger.info("Quota successfully restored after page refresh!")
            else:
                logger.warning("Quota warning banner still present after page refresh.")
            return available
        except Exception as exc:
            logger.error("Failed to refresh Gemini page for quota check: %s", exc)
            return False

    def _dump_dom_diagnostic(self, last_resp: Any) -> None:
        """將 DOM 備援時的 outerHTML 截前 20,000 字存入 DATA_DIR/logs/ 診斷檔。

        Args:
            last_resp: 最後一則模型回覆之 Locator 實體。
        """
        response_reader.dump_dom_diagnostic(self.diagnostic_dir, last_resp)

    def _click_and_read_clipboard(self, btn_locator: Any, source_name: str) -> str | None:
        """點擊指定複製按鈕並讀取剪貼簿文字。

        Args:
            btn_locator: 按鈕 Locator 實體。
            source_name: 來源標識（用於日誌與狀態追蹤）。

        Returns:
            若複製成功且長度足夠傳回字串，否則為 None。
        """
        return response_reader.click_and_read_clipboard(self, btn_locator, source_name)

    def _try_copy_action_bar(self, target_scope: Any) -> str | None:
        """嘗試透過最後一則回覆動作列之「複製」按鈕讀取內容。

        Args:
            target_scope: 鎖定之最後一則回覆 Locator 範圍。

        Returns:
            若成功傳回 Markdown，否則為 None。
        """
        return response_reader.try_copy_action_bar(self, target_scope)

    def _try_copy_code_block(self, target_scope: Any) -> str | None:
        """嘗試透過回覆內「Markdown」程式碼區塊之複製圖示讀取內容。

        Args:
            target_scope: 鎖定之最後一則回覆 Locator 範圍。

        Returns:
            若成功傳回 Markdown，否則為 None。
        """
        return response_reader.try_copy_code_block(self, target_scope)

    def _copy_via_button(self) -> str | None:
        """嘗試從最後一則回應的「複製」按鈕讀取剪貼簿文字 (Refs: note-studio ISSUE-058)。

        Returns:
            若複製成功傳回字串，否則為 None。
        """
        return response_reader.copy_via_button(self)

    def _read_response_fallback(self) -> str | None:
        """備援機制：直接讀取最後一則回應容器文字並寫入診斷檔。

        Returns:
            若成功傳回字串，否則為 None。
        """
        return response_reader.read_response_fallback(self)

    def _is_valid_new_response(self, text: str) -> bool:
        """檢驗擷取文字是否為本輪有效的新生成內容。

        Args:
            text: 擷取之候選文字。

        Returns:
            若為有效新內容則回傳 True，否則為 False。
        """
        if not text or len(text.strip()) < 15:
            return False
        if self._last_sent_prompt and text.strip() == self._last_sent_prompt.strip():
            return False
        if self._baseline_response_text and text.strip() == self._baseline_response_text.strip():
            return False
        return True

    def get_last_response_markdown(self, timeout_seconds: int = 360) -> str:
        """等待生成完成並從最後一則回應的「複製」按鈕獲取原始 Markdown。

        Args:
            timeout_seconds: 最大等待生成時間（秒，預設 360 秒以容納深度思考與長篇教科書分析）。

        Returns:
            未經 DOM 渲染損壞的原始 Markdown 字串。

        Raises:
            GeminiAutomationError: 當無法獲取任何回應內容或等待超時時。
            GeminiQuotaExceededError: 當生成過程中達到配額上限時。
        """
        copied = self._copy_via_button()
        if copied is not None and self._is_valid_new_response(copied):
            return copied

        gen_sel = self.selectors.get("generating_indicator", "")
        start_t = time.time()
        last_log_t = start_t
        self._pause(2000, "get_last_response_markdown", sleep_fallback=True)

        while (time.time() - start_t) < timeout_seconds:
            self.assert_quota_available()
            if time.time() - last_log_t >= 30:
                elapsed = int(time.time() - start_t)
                logger.info("Waiting for Gemini response... elapsed %ds / max %ds", elapsed, timeout_seconds)
                last_log_t = time.time()

            if response_reader.is_response_generating(self, gen_sel):
                self._pause(2000, "get_last_response_markdown", sleep_fallback=True)
                continue

            collected = response_reader.try_collect_valid_response(self)
            if collected is not None:
                return collected

            self._pause(2000, "get_last_response_markdown", sleep_fallback=True)

        raise GeminiAutomationError(f"等待 Gemini 生成超時 ({timeout_seconds}s)")

    def _record_send_baselines(self) -> None:
        """送出前記錄當前最後一則回覆與數量作為 baseline，並清空剪貼簿 (note-studio ISSUE-054, 061)。"""
        prev = self._copy_via_button()
        if prev is None:
            prev = self._read_response_fallback()
        self._baseline_response_text = prev

        resp_sel = self.selectors.get("response_container", "")
        try:
            self._baseline_response_count = self.page.locator(resp_sel).count() if resp_sel else 0
        except Exception:
            self._baseline_response_count = 0

        try:
            self.page.evaluate("() => navigator.clipboard.writeText('')")
        except Exception as exc:
            logger.warning("send_prompt: cannot clear the clipboard: %s", exc)

    def _fill_and_submit_prompt(self, prompt: str) -> None:
        """將提示詞填入輸入框並點擊送出按鈕。

        Args:
            prompt: 提示詞文字。
        """
        textarea = self.page.locator(self.selectors["prompt_textarea"]).first
        try:
            textarea.click()
            textarea.fill(prompt)
        except Exception as exc:
            logger.debug("Locator fill encountered error (%s), attempting keyboard type fallback", exc)
            try:
                textarea.click()
                self.page.keyboard.type(prompt)
            except Exception as exc2:
                logger.error("Failed to type prompt into editor: %s", exc2)
                raise

        self._pause(500, "send_prompt")
        self.page.locator(self.selectors["send_button"]).first.click()
        logger.info("Sent prompt successfully (%d characters)", len(prompt))

    def send_prompt(self, prompt: str) -> None:
        """輸入提示詞並點擊發送。

        Args:
            prompt: 提示詞文字。
        """
        self.assert_quota_available()
        self._last_sent_prompt = prompt
        self._record_send_baselines()
        self._fill_and_submit_prompt(prompt)

    def upload_files(self, file_paths: list[Path]) -> None:
        """上傳檔案至當前 Chat。

        Args:
            file_paths: 待上傳之本機檔案路徑清單。
        """
        chat_actions.upload_files(self, file_paths, GeminiAutomationError)

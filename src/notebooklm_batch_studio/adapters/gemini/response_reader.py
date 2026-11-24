"""Gemini 回覆內容擷取與 DOM 備援診斷輔助函式。

負責從複製按鈕（動作列／程式碼區塊）與 DOM 容器讀取最後一則回覆的 Markdown，
並在發生 DOM 備援時將診斷 HTML 片段寫入 `DATA_DIR/logs/`。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def dump_dom_diagnostic(diagnostic_dir: Path | None, last_resp: Any) -> None:
    """將 DOM 備援時的 outerHTML 截前 20,000 字存入 DATA_DIR/logs/ 診斷檔。

    Args:
        diagnostic_dir: 診斷檔輸出目錄。
        last_resp: 最後一則模型回覆之 Locator 實體。
    """
    try:
        outer_html = last_resp.evaluate("el => el.outerHTML") or ""
        snippet = outer_html[:20000]
        if not diagnostic_dir:
            return
        diagnostic_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        millis = int(time.time() * 1000) % 1000
        diag_file = diagnostic_dir / f"dom_fallback_{timestamp}_{millis:03d}.html"
        diag_file.write_text(snippet, encoding="utf-8")
        logger.warning(
            "Saved DOM fallback diagnostic HTML snippet (%d chars) to %s",
            len(snippet),
            diag_file,
        )
    except Exception as exc:
        logger.warning("Failed to dump DOM fallback diagnostic HTML: %s", exc)


def click_and_read_clipboard(driver: Any, btn_locator: Any, source_name: str) -> str | None:
    """點擊指定複製按鈕並讀取剪貼簿文字。

    Args:
        driver: GeminiWebDriver 實例。
        btn_locator: 按鈕 Locator 實體。
        source_name: 來源標識（用於日誌與狀態追蹤）。

    Returns:
        若複製成功且長度足夠傳回字串，否則為 None。
    """
    try:
        btn_locator.click(timeout=3000)
        driver._pause(200, f"_click_and_read_clipboard_{source_name}")
        text = driver.page.evaluate("navigator.clipboard.readText()")
        if isinstance(text, str) and text.strip() and len(text.strip()) >= 15:
            driver.was_dom_fallback = False
            driver.last_read_source = source_name
            logger.debug("Successfully copied raw markdown via %s (%d chars)", source_name, len(text))
            return text
    except Exception as exc:
        logger.debug("Clipboard copy failed for %s: %s", source_name, exc)
    return None


def try_copy_action_bar(driver: Any, target_scope: Any) -> str | None:
    """嘗試透過最後一則回覆動作列之「複製」按鈕讀取內容。

    Args:
        driver: GeminiWebDriver 實例。
        target_scope: 鎖定之最後一則回覆 Locator 範圍。

    Returns:
        若成功傳回 Markdown，否則為 None。
    """
    copy_sel = driver.selectors.get("copy_button", "")
    action_copy_sel = driver.selectors.get("action_bar_copy_button", "") or copy_sel
    if not action_copy_sel:
        return None
    action_btns = target_scope.locator(action_copy_sel)
    if action_btns.count() <= 0:
        return None
    return click_and_read_clipboard(driver, action_btns.last, "action_bar_button")


def try_copy_code_block(driver: Any, target_scope: Any) -> str | None:
    """嘗試透過回覆內「Markdown」程式碼區塊之複製圖示讀取內容。

    Args:
        driver: GeminiWebDriver 實例。
        target_scope: 鎖定之最後一則回覆 Locator 範圍。

    Returns:
        若成功傳回 Markdown，否則為 None。
    """
    code_copy_sel = driver.selectors.get("code_block_copy_button", "")
    if not code_copy_sel:
        return None
    code_btns = target_scope.locator(code_copy_sel)
    if code_btns.count() <= 0:
        return None
    return click_and_read_clipboard(driver, code_btns.last, "code_block_button")


def copy_via_button(driver: Any) -> str | None:
    """嘗試從最後一則回應的「複製」按鈕讀取剪貼簿文字 (Refs: note-studio ISSUE-058)。

    Args:
        driver: GeminiWebDriver 實例。

    Returns:
        若複製成功傳回字串，否則為 None。
    """
    resp_sel = driver.selectors.get("response_container", "")
    try:
        target_scope = driver.page
        if resp_sel:
            responses = driver.page.locator(resp_sel)
            # 只有當回覆數量增加時，才代表新回覆已產生 (note-studio ISSUE-061)
            if responses.count() <= driver._baseline_response_count:
                return None
            target_scope = responses.last

        copied = try_copy_action_bar(driver, target_scope)
        if copied is not None:
            return copied
        return try_copy_code_block(driver, target_scope)
    except Exception as exc:
        logger.warning("Failed to copy from clipboard via copy button: %s", exc)
    return None


def read_response_fallback(driver: Any) -> str | None:
    """備援機制：直接讀取最後一則回應容器文字並寫入診斷檔。

    Args:
        driver: GeminiWebDriver 實例。

    Returns:
        若成功傳回字串，否則為 None。
    """
    resp_sel = driver.selectors.get("response_container", "")
    if not resp_sel:
        return None
    try:
        responses = driver.page.locator(resp_sel)
        # 只有當回覆數量增加時，才代表新回覆已產生 (note-studio ISSUE-061)
        if responses.count() <= driver._baseline_response_count:
            return None
        last_resp = responses.last
        text = str(last_resp.inner_text())
        if not text.strip():
            return None
        logger.warning(
            "Failed to obtain raw markdown via copy buttons; falling back to DOM reading "
            "(Refs: note-studio ISSUE-058)"
        )
        driver.was_dom_fallback = True
        driver.last_read_source = "dom"
        logger.info("Retrieved response text fallback from DOM (%d chars)", len(text))
        dump_dom_diagnostic(driver.diagnostic_dir, last_resp)
        return text
    except Exception as exc:
        logger.error("Failed to read response container fallback: %s", exc)
    return None


def is_response_generating(driver: Any, gen_sel: str) -> bool:
    """檢查頁面上的生成中停止按鈕是否仍可見。

    Args:
        driver: GeminiWebDriver 實例。
        gen_sel: 生成指示器選擇器。

    Returns:
        若仍在生成中回傳 True，否則為 False。
    """
    if not gen_sel:
        return False
    try:
        ind = driver.page.locator(gen_sel)
        return bool(ind.count() > 0 and ind.first.is_visible())
    except Exception as exc:
        logger.warning("get_last_response_markdown: cannot read the generating indicator: %s", exc)
        return False


def try_collect_valid_response(driver: Any) -> str | None:
    """嘗試透過複製按鈕或 DOM 備援收集有效的新回覆。

    Args:
        driver: GeminiWebDriver 實例。

    Returns:
        有效新回覆字串，若尚未就緒或無效則回傳 None。
    """
    copied = driver._copy_via_button()
    if isinstance(copied, str) and driver._is_valid_new_response(copied):
        driver._baseline_response_text = copied
        return copied

    fallback = driver._read_response_fallback()
    if isinstance(fallback, str) and driver._is_valid_new_response(fallback):
        driver._baseline_response_text = fallback
        return fallback
    return None

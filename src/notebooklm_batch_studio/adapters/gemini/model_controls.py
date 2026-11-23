"""Gemini 模型選擇與回覆模型偵測輔助函式。

將 Gemini 網頁前端的模型切換（含思考深度）與回覆詳情（response details）
模型名稱解析邏輯自 `web_driver.py` 拆出，維持單一職責與低巢狀深度。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from notebooklm_batch_studio.adapters.gemini.selectors import is_model_match

logger = logging.getLogger(__name__)


def _click_menu_option(driver: Any, picker: Any, item_sel: str, label: str) -> bool:
    """開啟模型選單並點擊符合選擇器的選項，找不到時關閉選單。

    Args:
        driver: GeminiWebDriver 實例。
        picker: 模型選擇器按鈕 Locator。
        item_sel: 目標選單項目 CSS 選擇器。
        label: 日誌用選項描述。

    Returns:
        成功點擊目標選項回傳 True，否則回傳 False。
    """
    picker.click()
    driver._pause(800, f"select_model_{label}")
    target_item = driver.page.locator(item_sel).first
    if target_item.count() > 0 and target_item.is_visible():
        target_item.click()
        driver._pause(800, f"select_model_{label}_done")
        return True
    picker.click()
    return False


def _select_thinking_level(driver: Any, picker: Any, thinking_level: str) -> None:
    """在模型選單中切換思考深度選項。

    Args:
        driver: GeminiWebDriver 實例。
        picker: 模型選擇器按鈕 Locator。
        thinking_level: 思考深度關鍵字（如 'Medium'、'High'、'Low'）。
    """
    if not thinking_level:
        return
    try:
        th_sel = f'gem-menu-item:has-text("{thinking_level}")'
        if _click_menu_option(driver, picker, th_sel, "thinking"):
            logger.info("Selected thinking level: %s", thinking_level)
    except Exception as exc:
        logger.warning("select_model: thinking-level picker failed: %s", exc)


def select_model(driver: Any, model_name: str, thinking_level: str = "") -> None:
    """在 Gemini 網頁前端選單切換至指定的 AI 模型與思考深度。

    Args:
        driver: GeminiWebDriver 實例。
        model_name: 目標模型關鍵字（如 '3.1 Pro'、'3.8 Flash'）。
        thinking_level: 思考深度關鍵字（如 'Medium'、'High'、'Low'）。
    """
    if not model_name:
        return
    picker_sel = driver.selectors.get("model_selector", "")
    if not picker_sel:
        return
    try:
        picker = driver.page.locator(picker_sel).first
        if not (picker.count() > 0 and picker.is_visible()):
            return
        item_sel = (
            f'gem-menu-item:has-text("{model_name}"), '
            f'[role="menuitem"]:has-text("{model_name}"), '
            f'button:has-text("{model_name}")'
        )
        if _click_menu_option(driver, picker, item_sel, "model"):
            logger.info("Successfully switched Gemini model to: %s", model_name)
        _select_thinking_level(driver, picker, thinking_level)
    except Exception as exc:
        logger.warning("Model selection was not performed or failed: %s", exc)


def get_current_model_menu_text(page: Any, selectors: dict[str, str]) -> str:
    """讀取輸入框旁模型選擇器按鈕目前顯示之文字或標籤。

    Args:
        page: Playwright Page 物件。
        selectors: DOM 選取器字典。

    Returns:
        模型按鈕文字或標籤（若找不到回傳空字串）。
    """
    picker_sel = selectors.get("model_selector", "")
    if not picker_sel:
        return ""
    try:
        picker = page.locator(picker_sel).first
        if picker.count() > 0 and picker.is_visible():
            text = str(picker.inner_text()).strip()
            if not text:
                text = str(picker.get_attribute("aria-label") or "").strip()
            return str(text)
    except Exception as exc:
        logger.warning("get_current_model_menu_text error: %s", exc)
    return ""


def _open_response_details_panel(driver: Any, scope: Any) -> bool:
    """點擊指定回覆的「⋯」選單並開啟 response details 面板。

    Args:
        driver: GeminiWebDriver 實例。
        scope: 回覆節點 Locator。

    Returns:
        成功開啟面板回傳 True，否則回傳 False。
    """
    more_sel = driver.selectors.get("more_actions_button", "")
    details_sel = driver.selectors.get("response_details_menu_item", "")
    more_btns = scope.locator(more_sel)
    if more_btns.count() <= 0:
        logger.warning("_read_model_from_scope: more options button (⋯) not found")
        return False

    more_btns.last.click(timeout=3000)
    driver._pause(400, "read_model_menu")

    details_item = driver.page.locator(details_sel)
    if details_item.count() <= 0 or not details_item.first.is_visible():
        logger.warning("_read_model_from_scope: response details menu item not found")
        driver.page.keyboard.press("Escape")
        return False

    details_item.first.click(timeout=3000)
    driver._pause(600, "read_model_panel")
    return True


def _extract_model_from_panel(page: Any, panel_sel: str) -> str:
    """自已開啟的 response details 面板文字解析實際模型名稱。

    Args:
        page: Playwright Page 物件。
        panel_sel: 面板 CSS 選擇器。

    Returns:
        模型名稱字串（解析失敗回傳 'unknown'）。
    """
    panel = page.locator(panel_sel)
    if panel.count() <= 0 or not panel.first.is_visible():
        return "unknown"
    panel_text = panel.first.inner_text()
    match = re.search(r"(?:Used|使用了?|使用模型[：:])\s*([^\n\r]+)", panel_text, re.IGNORECASE)
    if match:
        model_name = match.group(1).strip()
        logger.info("Detected actual Gemini model from response details: %s", model_name)
        return model_name
    logger.warning("Could not parse model name from panel text: %s", panel_text[:200])
    return "unknown"


def _close_details_panel(page: Any, close_sel: str) -> None:
    """關閉 response details 面板。

    Args:
        page: Playwright Page 物件。
        close_sel: 關閉按鈕 CSS 選擇器。
    """
    close_btn = page.locator(close_sel) if close_sel else None
    if close_btn is not None and close_btn.count() > 0 and close_btn.first.is_visible():
        close_btn.first.click(timeout=2000)
    else:
        page.keyboard.press("Escape")


def read_model_from_scope(driver: Any, scope: Any) -> str:
    """點擊指定回覆範圍內之「⋯」選單並讀取 response details 之模型名稱。

    Args:
        driver: GeminiWebDriver 實例。
        scope: 回覆節點 locator。

    Returns:
        偵測到的模型名稱字串（失敗回傳 'unknown'）。
    """
    if not driver.selectors.get("more_actions_button", ""):
        return "unknown"
    panel_sel = driver.selectors.get("response_details_panel", "")
    close_sel = driver.selectors.get("response_details_close_button", "")
    try:
        if not _open_response_details_panel(driver, scope):
            return "unknown"
        model_name = _extract_model_from_panel(driver.page, panel_sel)
        _close_details_panel(driver.page, close_sel)
        return model_name
    except Exception as exc:
        logger.warning("Failed to extract model name from response details: %s", exc)
        try:
            driver.page.keyboard.press("Escape")
        except Exception:
            pass
        return "unknown"


__all__ = [
    "get_current_model_menu_text",
    "is_model_match",
    "read_model_from_scope",
    "select_model",
]

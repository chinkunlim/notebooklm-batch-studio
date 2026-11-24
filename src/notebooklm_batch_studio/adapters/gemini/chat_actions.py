"""Gemini 對話重命名與檔案上傳輔助函式。

將對話標題重命名與檔案上傳操作自 `web_driver.py` 拆出，維持單檔長度在規範內。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_driver_logger = logging.getLogger("notebooklm_batch_studio.adapters.gemini.web_driver")  # Refs: ISSUE-052


def find_rename_menu_button(driver: Any, menu_sel: str) -> Any:
    """尋找對話選單觸發按鈕，若頂部選單無效則嘗試 hover 側邊欄對話項。

    Args:
        driver: GeminiWebDriver 實例。
        menu_sel: 選單按鈕 CSS 選擇器。

    Returns:
        Playwright Locator 實體（若找到可見元素），否則為 None。
    """
    menu_btn = driver.page.locator(menu_sel).first
    if menu_btn.count() > 0 and menu_btn.is_visible():
        return menu_btn

    conv_item = driver.page.locator(
        'gem-nav-list-item[data-test-id="conversation"], '
        '[data-test-id="conversation-item"], [role="listitem"]'
    ).first
    if conv_item.count() > 0 and conv_item.is_visible():
        conv_item.hover()
        driver._pause(300, "_find_rename_menu_button")
        btn = conv_item.locator(menu_sel).first
        if btn.count() > 0 and btn.is_visible():
            return btn
    return None


def open_rename_dialog(driver: Any, menu_sel: str, rename_sel: str) -> bool:
    """開啟對話選單並點擊「重新命名」選項。

    Args:
        driver: GeminiWebDriver 實例。
        menu_sel: 選單按鈕選擇器。
        rename_sel: 重新命名項目選擇器。

    Returns:
        成功開啟重命名輸入框回傳 True，否則為 False。
    """
    menu_btn = driver._find_rename_menu_button(menu_sel)
    if not menu_btn:
        _driver_logger.warning(
            "Rename chat aborted: menu button not found or not visible (selector: %s). "
            "Gemini DOM may have updated (Refs: note-studio ISSUE-034, PROJECT_RULES R100).",
            menu_sel,
        )
        return False
    menu_btn.click()
    driver._pause(600, "rename_current_chat")

    rename_item = driver.page.locator(rename_sel).first
    if not (rename_item.count() > 0 and rename_item.is_visible()):
        _driver_logger.warning(
            "Rename chat aborted: rename item not found (selector: %s) (Refs: note-studio ISSUE-034).",
            rename_sel,
        )
        return False
    rename_item.click()
    driver._pause(600, "rename_current_chat")
    return True


def submit_rename_input(driver: Any, target_title: str, input_sel: str, save_sel: str) -> bool:
    """在重命名輸入框填入新標題並送出確認。

    Args:
        driver: GeminiWebDriver 實例。
        target_title: 欲設定之新標題。
        input_sel: 輸入框選擇器。
        save_sel: 確認按鈕選擇器。

    Returns:
        若輸入框成功填寫並送出回傳 True，否則為 False。
    """
    title_input = (
        driver.page.locator(input_sel).first if input_sel else driver.page.locator('input[type="text"]').first
    )
    if not (title_input.count() > 0 and title_input.is_visible()):
        _driver_logger.warning(
            "Rename chat aborted: title input not found (selector: %s) (Refs: note-studio ISSUE-034).",
            input_sel,
        )
        return False

    title_input.fill(target_title)
    driver._pause(300, "_submit_rename_input")
    driver.page.keyboard.press("Enter")
    save_btn = driver.page.locator(save_sel).first if save_sel else None
    if save_btn and save_btn.count() > 0 and save_btn.is_visible():
        save_btn.click()
    logger.info("Successfully renamed current Gemini chat to: %s", target_title)
    return True


def rename_current_chat(driver: Any, new_title: str = "") -> bool:
    """嘗試在 Gemini 網頁前端側邊欄將當前對話重命名為指定標題。

    Args:
        driver: GeminiWebDriver 實例。
        new_title: 欲設定之新標題（若為空則採用 start_new_chat 時暫存之標題）。

    Returns:
        若成功重命名回傳 True，否則為 False。
    """
    target_title = new_title or getattr(driver, "_desired_chat_title", "")
    if not target_title:
        return False
    logger.info("Attempting to rename current Gemini chat to: %s", target_title)
    try:
        menu_sel = driver.selectors.get("chat_title_menu", "")
        rename_sel = driver.selectors.get("rename_chat_item", "")
        input_sel = driver.selectors.get("chat_title_input", "")
        save_sel = driver.selectors.get("rename_confirm_button", "")
        if not open_rename_dialog(driver, menu_sel, rename_sel):
            return False
        return bool(driver._submit_rename_input(target_title, input_sel, save_sel))
    except Exception as exc:
        _driver_logger.warning("Rename chat failed with exception (Refs: note-studio ISSUE-034): %s", exc)
        return False


def upload_files(driver: Any, file_paths: list[Path], error_cls: type[Exception]) -> None:
    """上傳檔案至當前 Chat。

    Args:
        driver: GeminiWebDriver 實例。
        file_paths: 待上傳之本機檔案路徑清單。
        error_cls: 缺少選取器時拋出的異常類別。
    """
    if not file_paths:
        return

    btn_sel = driver.selectors.get("file_upload_button", "")
    if btn_sel:
        try:
            btn = driver.page.locator(btn_sel).first
            if btn.count() > 0 and btn.is_visible():
                btn.click()
                driver._pause(500, "upload_files")
        except Exception as exc:
            logger.warning("Could not click upload button before file input: %s", exc)

    input_sel = driver.selectors.get("file_upload_input", "")
    if not input_sel:
        raise error_cls("未配置 file_upload_input 選取器。")

    str_paths = [str(p.resolve()) for p in file_paths]
    driver.page.locator(input_sel).first.set_input_files(str_paths)
    logger.info("Uploaded %d files to Gemini chat: %s", len(file_paths), str_paths)
    driver._pause(4000, "upload_files")

"""Gemini 網頁 DOM 元素選取器集中配置表（note-studio SPEC-012, Plan §9.6）。

將所有 Gemini 網頁前端元素之 Locator / Selector 集中管理，
當 Google 前端改版時，只需在此檔更新選取器規則，或由本機覆寫機制載入。
"""

from __future__ import annotations

import logging

from notebooklm_batch_studio.domain.note_pipeline import (
    MODEL_NAME_MAPPINGS as MODEL_NAME_MAPPINGS,
)
from notebooklm_batch_studio.domain.note_pipeline import (
    is_model_match as is_model_match,
)

logger = logging.getLogger(__name__)

# Gemini Web UI 元素選取器
GEMINI_SELECTORS: dict[str, str] = {
    # 建立新對話按鈕
    "new_chat_button": (
        'button[aria-label*="新對話"], button[aria-label*="New chat"], [data-test-id="new-chat-button"]'
    ),
    # 對話標題編輯與選單
    "chat_title_menu": (
        'button[aria-label="Open menu for conversation actions."], '
        'button[aria-label*="conversation actions"], '
        'button[aria-label*="對話選項"], button[aria-label*="Chat options"], '
        'button[aria-label*="更多選項"], button[aria-label*="More options"], '
        '[data-test-id*="more-menu"], [data-test-id*="chat-actions"], '
        'button:has(mat-icon:has-text("more_vert"))'
    ),
    "rename_chat_item": (
        'gem-menu-item[data-test-id="rename-button"], '
        '[data-test-id="rename-button"], '
        '[role="menuitem"]:has-text("重新命名"), [role="menuitem"]:has-text("Rename")'
    ),
    "chat_title_input": (
        'input[aria-label="Rename this chat"], '
        'input[aria-label*="Rename"], '
        'input[aria-label*="標題"], input[aria-label*="Title"], '
        '.cdk-overlay-container input[type="text"]'
    ),
    "rename_confirm_button": (
        'gem-button[data-test-id="save-button"] button, '
        '[data-test-id="save-button"], '
        'button:has-text("Rename"), button:has-text("重新命名"), '
        'button:has-text("儲存"), button:has-text("Save"), button:has-text("確認")'
    ),
    # 輸入框（支援最新 Quill 編輯器與 contenteditable，避開外層容器）
    "prompt_textarea": (
        ".ql-editor, rich-textarea .ql-editor, "
        'rich-textarea [contenteditable="true"], [contenteditable="true"]'
    ),
    # 發送按鈕
    "send_button": (
        'button[aria-label*="Send message"], button[aria-label*="傳送"], '
        'button[aria-label*="Send"], button[mattooltip*="傳送"]'
    ),
    # 生成中指示器 / 停止生成按鈕
    "generating_indicator": (
        'button[aria-label*="Stop"], button[aria-label*="停止"], '
        '.stop-generating-button, [aria-label*="Stop generating"]'
    ),
    # 最後一則回覆的容器與複製按鈕
    "response_container": 'model-response, [data-test-id="model-response"]',
    "action_bar_copy_button": (
        'button[aria-label*="複製"]:not([aria-label*="程式碼"]):not([aria-label*="code"]), '
        'button[aria-label*="Copy"]:not([aria-label*="code"]):not([aria-label*="Code"]), '
        '[data-test-id="copy-button"]'
    ),
    "code_block_copy_button": (
        'button[aria-label*="Copy code"], button[aria-label*="複製程式碼"], '
        ".code-block button, .code-container button, "
        'button:has(mat-icon:has-text("content_copy"))'
    ),
    "copy_button": ('button[aria-label*="複製"], button[aria-label*="Copy"], [data-test-id="copy-button"]'),
    # 更多操作選單（⋯）與回覆詳細資訊 (note-studio SPEC-012, Refs: note-studio ISSUE-058)
    # 真實頁面（2026-11-12 探查）：aria-label="Show more options"、mat-icon fonticon="more_horiz"；
    # 屬性比對區分大小寫，所以加上 i 旗標
    "more_actions_button": (
        'button[aria-label*="more options" i], button[aria-label*="更多選項"], '
        'button:has(mat-icon[fonticon="more_horiz"]), [data-test-id="more-options-button"]'
    ),
    # 真實頁面（2026-11-12 探查）：選單項 data-test-id="response-details-button"；
    # 面板中的模型行 data-test-id="model-line"，文字為「Used 3.5 Flash-Lite」
    "response_details_menu_item": (
        '[data-test-id="response-details-button"], '
        '[role="menuitem"]:has-text("response details"), [role="menuitem"]:has-text("回覆詳細資料")'
    ),
    "response_details_panel": '[data-test-id="model-line"]',
    # 不用通用的 Close 按鈕：真實頁面第一個符合的是收合左側欄的「Close sidebar」；改按 Escape 關閉
    "response_details_close_button": "",
    # 檔案上傳按鈕與隱藏 input
    "file_upload_button": (
        'button[aria-label*="Upload & tools"], button[aria-label*="上傳檔案"], '
        'button[aria-label*="Upload file"], [data-test-id="upload-button"]'
    ),
    "file_upload_input": 'input[type="file"]',
    # Quota 限流與警示橫幅 (Refs: note-studio ISSUE-043)
    "quota_warning_banner": (
        '.limit-reached, [data-test-id*="limit-reached"], '
        ':has-text("Limit reached"), :has-text("limit reached"), '
        '[role="alert"]:has-text("配額"), [role="alert"]:has-text("quota"), '
        ':has-text("已達上限"), :has-text("已達配額上限"), '
        ':has-text("額度已用完"), [role="alert"]:has-text("額度")'
    ),
    # 模型選擇器標籤
    "model_selector": (
        'button[aria-label*="mode picker"], [data-test-id="model-selector"], '
        'button[aria-label*="模型選擇"], button[aria-label*="Model"]'
    ),
}

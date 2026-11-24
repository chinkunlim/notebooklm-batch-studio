"""Gemini 網頁自動化適配器（note-studio SPEC-012, Plan §9）。

提供：
1. GEMINI_SELECTORS: 集中式 DOM 選取器表
2. BrowserSessionManager: 持久化 Profile 瀏覽器會話管理
3. GeminiWebDriver: 網頁驅動器
4. GeminiAutomationError, GeminiQuotaExceededError: 專屬異常
"""

from notebooklm_batch_studio.adapters.gemini.browser_session import BrowserSessionManager
from notebooklm_batch_studio.adapters.gemini.selectors import GEMINI_SELECTORS
from notebooklm_batch_studio.adapters.gemini.web_driver import (
    GeminiAutomationError,
    GeminiQuotaExceededError,
    GeminiWebDriver,
)

__all__ = [
    "GEMINI_SELECTORS",
    "BrowserSessionManager",
    "GeminiWebDriver",
    "GeminiAutomationError",
    "GeminiQuotaExceededError",
]

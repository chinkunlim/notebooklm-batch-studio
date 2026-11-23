# ISSUE-043：Cloudflare 對程式控制的 Chrome 反覆要求驗證

- **狀態**：🟡 已規避 (Mitigated)
- **來源**：整合自 `literature-fetch`（原 `ISSUE-003`，2026-10-20）
- **任務**：`TASK-025`

## 1. 現象

部分使用 Cloudflare 互動驗證的典藏庫（如 UWE worktribe、部分 ScienceDirect 頁面），在 Playwright 開啟的 Chrome 中即使人工點擊驗證仍反覆跳回驗證頁，且頁面跳轉期間執行 `page.evaluate` 可能出現 `Execution context was destroyed`。

## 2. 根本原因

1. Cloudflare 可偵測瀏覽器受自動化控制，依 ADR-011 / ADR-001 原則不繞過反機器人驗證。
2. 驗證頁會短暫消失再重導向，若只檢查一次非驗證頁就結束等待，會在跳轉中呼叫 `page.evaluate`。

## 3. 修正或規避方式

- `adapters/literature/browser.py` 的 `_settle` 需連續兩次檢查都不是驗證頁才結束；`_needs_user` 讀標題失敗時視為仍在跳轉。
- 此類網站改由使用者用自己的瀏覽器手動下載 PDF 放入 `<DATA_DIR>/scratch/literature/`，系統會自動掃描並補入追蹤（`LiteratureManager._register_dir_pdfs`）。

## 4. 防回歸

實機互動模式驗證 `Execution context` 不再中斷跳轉流程。

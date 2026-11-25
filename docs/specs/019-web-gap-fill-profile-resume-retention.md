# SPEC-019：網頁補齊產出模式、筆記生成繼續、Gemini 憑證保留天數

- **狀態**：Implemented <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-25
- **相關任務 / ADR**：核心規則 13、2026-11-25 網頁整合盤點（149 個 HTTP API 對照網頁呼叫）

## 1. 目標

盤點發現三個功能只有 HTTP 與 MCP、網頁沒有入口：

1. 變更課程產出模式（`POST /api/courses/{code}/profile`）：只記錄的課程無法在網頁改成完整產出。
2. 繼續已暫停的筆記生成（`POST /api/notes/resume/{course_key}`）：網頁只有「暫停」。
3. Gemini 網頁版憑證保留天數（`POST /api/notes/gemini/retention`）。

## 2. 使用情境

- **情境 A**：心理學研究法是「只記錄」，使用者在課程「進階工具 → 變更產出模式…」選「完整產出」，確認提示說明會排入新工作並使用額度後送出。
- **情境 B**：筆記生成按了「暫停」後，按「繼續」解除暫停。
- **情境 C**：在筆記生成頁看到「憑證保留 30 天」，改成 60 後按「儲存」。

## 3. 需求

- **必須 (Must)**：
  1. 課程「進階工具」新增「變更產出模式…」：顯示目前模式與四個選項（完整產出／只做測驗／考前衝刺／只記錄、不產生），選非「只記錄」時確認文字說明會排入新工作、未暫停時會開始使用 Gemini Notebook 額度；完成後顯示新排入的工作數並重新整理。
  2. 無效的產出模式回 `422`（原本是未處理的例外）。
  3. 筆記生成頁「暫停」旁新增「繼續」，呼叫 `POST /api/notes/resume/{course_key}` 並重新整理狀態。
  4. 筆記生成頁新增保留天數輸入（0 = 跟隨 Google 到期日，最大 3650），值由 `GET /api/notes/gemini/auth-status` 的 `retention_days` 帶入，按「儲存」以 `confirm: true` 送出。
- **不做 (Out of scope)**：舊版資料夾遷移（`migrate-study-layout`，已由 SPEC-023 停用，一次性且有 ISSUE-069 風險）與 note-studio 舊筆記匯入（已由 `consolidate` 取代）不放到網頁。

## 4. 介面 / API

沿用既有 API；只新增 `422` 錯誤對應。

## 5. 驗收標準

- [x] **場景 19a**：產出模式 API 對無效值回 422；`record-only` → `full` 會排入工作；網頁有「變更產出模式…」並呼叫 `/profile`。（`tests/test_web_gap_fill.py::test_profile_switch_http_and_web`）
- [x] **場景 19b**：暫停後繼續會清除暫停旗標；網頁有「繼續」按鈕並呼叫 `/api/notes/resume/`。（`test_note_resume_http_and_web`）
- [x] **場景 19c**：保留天數可由網頁讀取與儲存（`confirm: true`），超出範圍回 422。（`test_gemini_retention_http_and_web`）

## 6. 未決問題

- 無。

# SPEC-005：產出參數設定、重新生成版本、命名說明與網頁進度

- **狀態**：Implemented <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-01
- **相關任務 / ADR**：TASK-009 / ADR-005

## 1. 目標

測試階段每種產出都會生成，之後使用者在網頁上挑選要的內容、調整參數、重新生成不滿意的項目，
並且隨時看得到哪些完成、哪些在排隊、額度用完後何時會自動繼續。

## 2. 使用情境

- 學生想在 iPad 直式閱讀資訊圖表：把課程的「資訊圖表方向」設成直式，按「重新生成」，得到 v2 與 A4 / iPad / MacBook 版本。
- 使用者看不懂 quiz_1 / quiz_2 / quiz_3 差在哪：按「🏷️ 命名規則」查看。
- 額度用完：網頁顯示「⏸ 等待額度，預計 HH:MM 自動繼續」，web 服務開著時間到就自己接著跑。

## 3. 需求

- **必須 (Must)**：
  - 每門課可設定的參數（預設值）：資訊圖表方向 portrait、詳細程度 detailed、風格 auto_select；語音 deep_dive / default；
    投影片 detailed_deck / default、下載 pdf；影片 explainer / auto_select；測驗題量 more；閃卡 more / medium；裝置版本 開。
  - 重新生成保留舊版，Gemini Notebook 標題加「 (v2)」，本機檔名加「_v2」。
  - 資訊圖表裝置版本：`<名稱>_A4.pdf`（2480×3508，300 dpi）、`<名稱>_iPadAir4.png`（1640×2360）、
    `<名稱>_MacBookPro14.png`（3024×1964），補白邊、不裁切。
  - web 啟動自動處理佇列（`AUTO_START_QUEUE=true`）；CLI `batch --wait-quota` 等額度重置後繼續。
  - 網頁課程頁：狀態統計條、中文狀態、版本徽章、重新生成按鈕、產出設定面板、每 15 秒自動更新。
- **可選 (Nice to have)**：依使用者勾選只生成部分內容（目前測試階段全部生成）。
- **不做 (Out of scope)**：Gemini Notebook 指定精確像素尺寸（API 只提供橫 / 直 / 方）；自動刪除舊版本。

## 4. 介面 / API

| 入口 | 說明 |
|---|---|
| `GET /api/naming-guide`、MCP `get_naming_guide` | 命名規則與每種產出的意思 |
| `GET /api/courses/{code}/options`、MCP `get_course_options` | 目前參數與可選值 |
| `PUT /api/courses/{code}/options` `{"options": {...}}`、MCP `set_course_options(confirm)` | 不合法的值回 422 |
| `POST /api/courses/{code}/jobs/regenerate` `{"artifact_type", "lecture_no"}`、MCP `regenerate_artifact(confirm)` | 回傳新工作的 version |

工作資料多了 `label`、`version`、`artifact_ids`、`cooldown_until`。

## 5. 驗收標準

- [x] 心智圖以 `rename_mind_map` 改名（`tests/test_versions_and_options.py`）
- [x] v2 的標題與檔名帶版本，並產生三個裝置版本
- [x] 參數正確對應成 notebooklm-py enum；不合法的值被拒絕；重新註冊不覆蓋設定
- [x] 額度等待到期後工作自動完成（`wait_for_quota`）
- [x] web 啟動時自動開始佇列
- [ ] 真機：v2 資訊圖表為直式、Gemini Notebook 標題正確

## 6. 未決問題

- 影片 `short` 格式在 Gemini Notebook 是固定風格，選了其他風格可能被忽略。

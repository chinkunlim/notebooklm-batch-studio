# ISSUE-066：未上傳講義自動觸發 key-points 產生導致 422

- **狀態**：🟢 已解決 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 現象

在研讀模式開啟尚未上傳來源至 Gemini Notebook 的課程（含未上傳講次或 `record-only` 舊學期課程）時，首頁載入會自動發送 `POST /api/courses/<code>/lectures/<no>/key-points`，立即收到 HTTP 422 並在畫面跳出錯誤提示。

- **錯誤訊息**：`POST /api/courses/115-1_CP30000/lectures/1/key-points -> 422 Unprocessable Entity`（Toast：`產生重點失敗：This lecture is not uploaded to Gemini Notebook yet`）
- **重現步驟**：登錄一門尚未上傳來源或為 `record-only` 的課程後開啟網頁首頁
- **影響範圍**：`entrypoints/static/studio-reader.js` (`loadKeyPoints`)

## 2. 根本原因

`studio-reader.js::loadKeyPoints` 在本地尚未存有 key-points 時未檢查當前講次是否已具備 `source_id`（已上傳至 Gemini Notebook），即無條件呼叫 `generateKeyPoints(false, true)`。

## 3. 修正或規避方式

於 `studio-reader.js::loadKeyPoints` 先從 `currentStudyCourse?.lectures` 尋找當前講次，僅當 `lec && lec.source_id` 存在時才自動呼叫 `generateKeyPoints(false, true)`；未上傳與 `record-only` 課程不再於載入時自動發送請求（使用者仍可於上傳完成後手動點擊產生）。（Refs: ISSUE-066）

## 4. 防回歸

- `tests/test_dummy_user_simulation.py::UiAndStaticRegressionTest::test_ui_and_static_issue_regressions`（檢查 `lec && lec.source_id` 防護存在）
- 隔離伺服器（`http://127.0.0.1:8770`）瀏覽器實測 `0` console errors 與 `0` 4xx/5xx 回應

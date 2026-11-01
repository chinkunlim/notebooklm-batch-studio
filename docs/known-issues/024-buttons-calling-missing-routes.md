# ISSUE-024：部分按鈕呼叫不存在的 API（Prompt 編輯、立即喚醒、裝置版資訊圖表）

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`

## 1. 現象

逐一點擊網頁每個按鈕做檢查時，發現三個請求失敗：

| 按鈕 | 請求 | 回應 |
|---|---|---|
| 課程頁「📝 Prompt」 | `GET` / `POST /api/jobs/{id}/prompt` | 404：路由不存在，編輯器永遠是空白，儲存也失敗 |
| 「⋯ 更多 → ⚡ 立即喚醒等待額度的工作」 | `POST /api/queue/resume_quota` | 404：路由不存在 |
| 學習頁「資訊圖表」的 A4、iPad、MacBook 版連結 | `HEAD /api/artifacts/.../download/...` | 405：下載路由只接受 GET，所以裝置版連結從來不會顯示 |

網路錯誤只會顯示「Failed to fetch」，看不出是伺服器沒開，還是單一按鈕壞掉。

## 2. 根本原因

前端是從舊版模板帶過來的，按鈕呼叫的路由在後端從來沒有實作。下載路由用 `@router.get` 宣告，所以 HEAD 請求被拒絕。

另外沒有任何測試去比對「頁面呼叫的路徑」和「實際存在的路由」，所以這類錯誤一直沒被發現。

## 3. 修正方式

- 新增 `GET` / `POST /api/jobs/{job_id}/prompt`（`entrypoints/http/queue.py`）。MCP 也新增 `get_job_prompt`，以及需要 confirm 的 `set_job_prompt`（`entrypoints/mcp_job_prompts.py`）。
- 「立即喚醒」改呼叫既有的 `POST /api/queue/resume`：它會喚醒等待額度的工作，並繼續執行佇列。
- 下載路由改成 `api_route(methods=["GET", "HEAD"])`。
- `static/studio-core.js` 包裝 `fetch`：讀取類請求（GET）失敗時自動重試 1 次；仍然失敗就在頂端顯示「伺服器沒有回應」橫幅和「重新整理」按鈕。寫入類請求不重試，避免送出兩次。

## 4. 防回歸

`tests/test_button_routes.py`：
- 頁面裡每一個 `fetch('/api/...')` 的路徑都必須對應到 OpenAPI 裡的路由。
- Prompt 路由與 MCP 工具的讀寫測試。
- 下載路由的 HEAD 測試。

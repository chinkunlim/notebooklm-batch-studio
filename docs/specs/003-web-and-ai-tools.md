# SPEC-003：本機網頁與 AI 工具串接（Open WebUI、MCP）

- **狀態**：Implemented (Phase 1, TASK-005)
- **日期**：2026-10-21
- **相關任務 / ADR**：ADR-001

## 1. 目標

用一個本機網頁管理所有課程（加入資料夾、看進度、重試），並讓 Open WebUI 與 Claude Code 等 Agent
用對話操作同樣的功能。依核心規則 13：同一組 services 由網頁、HTTP（OpenAPI）、MCP 三個入口呼叫。

## 2. 使用情境

- 在網頁上一次加入 5 個課程資料夾，選產出組合，按開始。
- 在 Open WebUI 問：「BIO101 做到哪了？」「把第 3 講的 quiz 給我」。
- 在 Claude Code 說：「第 5 講重新生成 infographic」。

## 3. 需求

### 需求確認摘要（LOCAL_AI_ENVIRONMENT §2）

| 項目 | 決定 |
|---|---|
| 誰用、在哪裡 | 只有使用者自己，在這台 Mac；綁 `127.0.0.1` |
| 會改資料的動作 | 加入／移除課程、開始生成、重做、變更設定與 prompt、登入 NotebookLM |
| AI 工具 | Open WebUI（OpenAPI 工具伺服器）；Claude Code、Antigravity、OpenCode、Cursor（MCP） |
| 本機模型 | 不需要（不接 Ollama） |
| 資料 | 下載檔在 `DATA_DIR/output/courses/`；原始講義在 `DATA_DIR/input/courses/`；佇列與紀錄在 SQLite |
| 介面 | 完整網頁 |
| 啟動 | 需要時手動開 |
| 埠號 | `8767` |
| 驗收 | 見 §5 |

### 必須 (Must)

**網頁**
- 課程清單：每門課的完成度、等待額度數量、失敗數量、notebook 連結。
- 加入課程：選一個或多個資料夾 → 預覽「將建立哪些 notebook、幾份 PDF、預計產出數量、預計幾天」→ 確認後開始。
- 課程頁：每講每項產出的狀態、下載連結、失敗原因、一鍵重試；開關資料夾監看；選產出組合。
- Prompt 設定頁：檢視與編輯各類 prompt，存檔時版本號加一。
- 登入狀態：顯示是否已登入；過期時提示使用者在跳出的瀏覽器重新登入（程式不輸入帳號密碼）。
- 總覽頁連結：開啟 SPEC-001 的課程總覽頁。

**OpenAPI / MCP 工具**（同一組 services；會改資料的 MCP 工具有 `confirm` 參數，`confirm=false` 時只回傳預覽）

| 工具 | 動作 | 會改資料 |
|---|---|---|
| `list_courses` | 列出課程與完成度 | 否 |
| `get_course_status` | 一門課每講每項的狀態 | 否 |
| `get_quiz` | 取得某講某份 quiz（可選不含答案） | 否 |
| `get_artifact_files` | 取得某講的下載檔路徑 | 否 |
| `preview_add_courses` | 預覽加入資料夾的結果 | 否 |
| `add_courses` | 加入資料夾並排入佇列 | 是（`confirm`） |
| `start_queue` / `pause_queue` | 開始／暫停佇列 | 是（`confirm`） |
| `retry_item` | 重做某項產出 | 是（`confirm`） |
| `set_course_profile` | 變更產出組合或監看開關 | 是（`confirm`） |

- 新增功能時三個入口一起接。

### 可選 (Nice to have)
- 網頁即時更新進度（Server-Sent Events）。
- 在網頁內播放 audio、預覽 infographic 與 mind map。

### 不做 (Out of scope)
- 對外網開放、手機存取、多使用者。
- 刪除 NotebookLM 上的 notebook。
- 網頁或 MCP 工具處理 Google 密碼。

## 4. 介面 / API

HTTP 路由（OpenAPI 由 FastAPI 自動產生，給 Open WebUI 匯入）：

- `GET  /api/courses`
- `GET  /api/courses/{code}`
- `GET  /api/courses/{code}/lectures/{no}/quiz/{variant}?with_answers=false`
- `POST /api/courses/preview`  body: `{"folders": ["..."]}`
- `POST /api/courses`          body: `{"folders": ["..."], "profile": "full"}`
- `POST /api/queue/start` / `POST /api/queue/pause`
- `POST /api/items/{id}/retry`

錯誤：資料夾不存在或沒有 PDF（400）、課程不存在（404）、尚未登入 NotebookLM（409，附說明）。

## 5. 驗收標準

- [ ] 實作第一步：專案補上 `api` 與 `web`（FastAPI、`entrypoints/mcp_server.py`、各工具設定檔），服務在 `http://127.0.0.1:8767` 啟動。
- [ ] 網頁加入一個資料夾 → 預覽 → 確認後自動完成全部產出並可下載。
- [ ] 在 Open WebUI 問「BIO101 做到哪了？」能回答正確進度。
- [ ] 在 Claude Code 透過 MCP `add_courses` 時，沒有 `confirm=true` 不會建立任何東西。
- [ ] 服務只綁 `127.0.0.1`。

## 6. 未決問題

- Open WebUI 用 OpenAPI 工具伺服器或 MCP（Streamable HTTP）→ 預設 OpenAPI，實作時再確認。
- 網頁選資料夾的方式：瀏覽器無法直接取得本機完整路徑，可能改成貼上路徑或由後端列出常用課程資料夾。

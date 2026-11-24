# ISSUE-053：gemini_web 筆記後端沒有登入入口

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-029`（發現）、`TASK-031`（修復）

## 1. 現象

note-studio 預設後端 gemini_web 使用 DATA_DIR/state/gemini_profile 的 Chrome 設定檔；未登入時錯誤訊息要使用者按設定面板「啟動登入視窗」或執行 note_studio_gemini_login，但本專案兩者都不存在。實機檢查 DATA_DIR/state/gemini_profile 不存在，代表此後端從未在本機登入成功。

- **錯誤訊息**：見上方現象描述
- **重現步驟**：見上方現象描述
- **影響範圍**：見上方現象描述

## 2. 根本原因

整合 note-studio 時只搬了 adapters/gemini 與 services/notes，沒有搬 gemini_auth_service（以未掛 Playwright 的 Chrome 開登入視窗，避開 Google 拒絕自動化瀏覽器登入，note-studio ISSUE-039）及其 HTTP/MCP/網頁入口與 test_gemini_auth.py。

## 3. 修正或規避方式

已於 `TASK-031` 移植並符合單向分層與安全權限規範：
- 服務層：`services/notes/gemini_auth_service.py`（`GeminiAuthService`、`GeminiLoginRuntimeProtocol`，設定檔 `0o700`）。
- 適配器層：`adapters/gemini/auth_runtime.py`（`ChromeGeminiLoginRuntime`，真實 Chrome 登入、CDP 儲存 `storage_state.json` 權限 `0o600`），並於 `config/settings.py` 設定 Mac 預設 Chrome 路徑。
- 三端入口：
  - HTTP：`entrypoints/http/gemini_auth.py`（`GET /api/notes/gemini/auth-status`、`POST /api/notes/gemini/login`、`POST /api/notes/gemini/logout`、`POST /api/notes/gemini/retention`）。
  - MCP：`entrypoints/mcp_gemini_auth.py`（`notes_gemini_auth_status`、`notes_gemini_login`、`notes_gemini_logout`、`notes_set_gemini_retention`，變更操作皆強制 `confirm=True`）。
  - Web UI：`entrypoints/static/index.html`（`#btnGeminiLogin`「啟動 Gemini 登入視窗」、`#btnGeminiLogout`、`#ngGeminiAuthBadge`）與 `studio-notes-gen.js`。
- 更正 `adapters/gemini/browser_session.py` 未登入錯誤訊息，指向「筆記生成」頁按鈕、`POST /api/notes/gemini/login` 與 MCP 工具 `notes_gemini_login`。

## 4. 防回歸

`tests/gemini/test_gemini_auth.py`（17 項單元與 HTTP/MCP/UI 整合測試）。

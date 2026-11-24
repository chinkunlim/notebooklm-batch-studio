# ISSUE-053：gemini_web 筆記後端沒有登入入口

- **狀態**：🔴 未解決 (Open)
- **發現日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-029`

## 1. 現象

note-studio 預設後端 gemini_web 使用 DATA_DIR/state/gemini_profile 的 Chrome 設定檔；未登入時錯誤訊息要使用者按設定面板「啟動登入視窗」或執行 note_studio_gemini_login，但本專案兩者都不存在。實機檢查 DATA_DIR/state/gemini_profile 不存在，代表此後端從未在本機登入成功。

- **錯誤訊息**：見上方現象描述
- **重現步驟**：見上方現象描述
- **影響範圍**：見上方現象描述

## 2. 根本原因

整合 note-studio 時只搬了 adapters/gemini 與 services/notes，沒有搬 gemini_auth_service（以未掛 Playwright 的 Chrome 開登入視窗，避開 Google 拒絕自動化瀏覽器登入，note-studio ISSUE-039）及其 HTTP/MCP/網頁入口與 test_gemini_auth.py。

## 3. 修正或規避方式

待辦（交由 Antigravity）：移植 note-studio 的 gemini_auth_service、登入狀態檢查與啟動登入視窗的 HTTP 路由、MCP 工具、網頁按鈕與測試；修改 browser_session.py 的錯誤訊息指向實際入口。目前可改用 backend=notebooklm。（相關程式碼註解加 `Refs: ISSUE-053`）

## 4. 防回歸

移植後補 tests/gemini/test_gemini_auth.py。

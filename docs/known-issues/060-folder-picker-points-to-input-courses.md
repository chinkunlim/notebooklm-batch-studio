# ISSUE-060：資料夾挑選器捷徑指向 input/courses 而非 study 與 scratch

- **狀態**：🔴 未解決 (Open)
- **發現日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 現象

services/folder_browser.py 頂層捷徑第一項寫死為 input/courses，未引導使用者選擇 study/ 與 scratch/。

- **錯誤訊息**：無錯誤例外，挑選器第一項顯示 `課程資料夾 (input/courses)`
- **重現步驟**：於 Web UI「加入課程」精靈打開資料夾挑選器或呼叫 `GET /api/folders`（無 `path` 參數）
- **影響範圍**：`services/folder_browser.py`、`entrypoints/http/settings.py`、`entrypoints/mcp_studio_tools.py`

## 2. 根本原因

資料夾挑選器簽章直接接收 courses_input_dir，未從 AppConfig 讀取 study_root_dir 與 scratch_dir。

## 3. 修正或規避方式

計畫於 Task 6（services/folder_browser.py、entrypoints/http/settings.py、entrypoints/mcp_studio_tools.py）修正。（相關程式碼註解加 `Refs: ISSUE-060`）

## 4. 防回歸

待補：tests/test_old_layout_retired.py::test_folder_browser_shortcuts (Task 6)

# ISSUE-062：舊佈局 input/courses 與 output/courses 仍被多處讀寫

- **狀態**：🔴 未解決 (Open)
- **發現日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 現象

上傳 PDF、問答筆記後備、課程摘要報告、刪除課程等 14+ 處程式仍讀寫 courses_input_dir 或 courses_output_dir。

- **錯誤訊息**：無錯誤例外，新檔案仍落入舊 `input/courses/` 或 `output/courses/`
- **重現步驟**：透過 API/MCP 上傳 PDF、建立未設定 `study_dir` 的問答筆記或執行報告生成
- **影響範圍**：`source_manager.py`、`qa_notes_service.py`、`orchestrator.py`、`course_settings.py`、`study_service.py`、`study_migration.py`

## 2. 根本原因

ADR-011 導入後僅遷移既有課程，未將所有服務層讀寫路徑全面切換至 study 目錄與 scratch/<種類>/。

## 3. 修正或規避方式

計畫於 Task 6 全面改為 <HANDOUTS>/_uploaded/、scratch/<kind>/ 與課程 study_dir 產出根目錄。（相關程式碼註解加 `Refs: ISSUE-062`）

## 4. 防回歸

待補：tests/test_old_layout_retired.py::test_no_new_writes_to_old_layout (Task 6)

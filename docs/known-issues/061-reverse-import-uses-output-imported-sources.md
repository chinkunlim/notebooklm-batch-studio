# ISSUE-061：反向匯入筆記本仍存於 output/imported_sources 舊佈局

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 現象

services/reverse_import.py 將匯入的筆記本來源與產出放進 output/imported_sources，未寫入 study/<學期>/<課程>/，且未標記學期與 record-only 狀態。

- **錯誤訊息**：無錯誤例外，反向匯入檔案寫入 `DATA_DIR/output/imported_sources/`
- **重現步驟**：呼叫反向匯入 API 或 MCP 工具匯入既有 NotebookLM 筆記本
- **影響範圍**：`services/reverse_import.py`、`entrypoints/http/reverse_import.py`、`entrypoints/mcp_qa_notes.py`

## 2. 根本原因

反向匯入設計於統一 study 目錄與學期身分規則建立之前。

## 3. 修正或規避方式

已於 `b13ba8f`（`services/reverse_import.py`、`entrypoints/http/reverse_import.py`、`entrypoints/mcp_qa_notes.py`）修正：反向匯入改為接收 `term`（預設當前學期）、落入 `study/<term>/<course>/` 並預設設定 `record-only` 屬性。（`Refs: ISSUE-061`）

## 4. 防回歸

- `tests/test_study_library.py::test_reverse_import_writes_to_study_term_record_only`

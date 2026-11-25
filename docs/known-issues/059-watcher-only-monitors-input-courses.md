# ISSUE-059：檔案監看器只監看 input/courses，未監看 study 學期樹

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 現象

entrypoints/cli.py watch 只監看 DATA_DIR/input/courses/，不會監看 study/<學期>/<課程>/02 Handouts/ 的新講義 PDF。

- **錯誤訊息**：無錯誤例外，放入 `study/` 的新講義不會觸發自動上傳與排程
- **重現步驟**：啟動 `notebooklm-batch-studio watch` 後於 `study/115-1/<課程>/02 Handouts/` 放入新 PDF
- **影響範圍**：`services/watcher.py` 與 `entrypoints/cli.py` watch 模式

## 2. 根本原因

舊版目錄監看實作早於 ADR-011/014 統一學習目錄導入，且未區分講義與其他分類。

## 3. 修正或規避方式

已於 `b13ba8f`（`services/watcher.py`、`entrypoints/cli.py`）修正：`watch` 改為遞迴監看 `study_root_dir` 內已登錄課程之 `CategoryRole.HANDOUTS` 分類目錄 PDF，自動排除 `01 Materials`、`04 Homework` 與非課程資料夾。（`Refs: ISSUE-059`）

## 4. 防回歸

- `tests/test_study_library.py::test_watcher_triggers_only_on_registered_course_handouts_pdf`

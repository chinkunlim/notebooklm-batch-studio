# ISSUE-006：重新註冊課程會清掉 source_id，導致重複上傳

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-008`

## 1. 現象

save_course 刪除並重建講次紀錄時沒保留 source_id，再跑 batch 或 watcher 觸發時會把所有 PDF 重新上傳到同一本筆記本

- **錯誤訊息**：無（靜默）；筆記本內出現重複來源
- **重現步驟**：課程已上傳後再次執行 `batch <同一資料夾>`，或 watcher 偵測到新 PDF
- **影響範圍**：`add_course_folders`、`register_course_folder`、CLI `batch`、`watch`、網頁 / MCP 新增課程

## 2. 根本原因

`CourseRepository.save_course` 會保留 `notebook_id`，但 `_update_lectures` 先刪除該課程所有講次紀錄，
再用重新掃描的結果寫回；掃描結果沒有 `source_id`，於是 `setup_notebook_and_sources` 認為每一講都未上傳而全部重傳。

## 3. 修正或規避方式

`_update_lectures` 刪除前先讀出已上傳的講次（以 sha256 對應），內容未變的 PDF 沿用原本的 `source_id` 與上傳狀態；
內容改變或新增的 PDF 才需要上傳。舊來源依專案規則不會自動從 NotebookLM 刪除。

## 4. 防回歸

`tests/test_course_reregistration.py`：`test_rescan_keeps_source_ids_of_unchanged_pdfs`。

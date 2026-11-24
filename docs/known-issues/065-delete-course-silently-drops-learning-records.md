# ISSUE-065：刪除課程直接移除資料庫學習紀錄且未建議封存

- **狀態**：🟢 已解決 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 現象

services/course_settings.py::delete_course 直接刪除課程在資料庫的測驗、錯題、進度等紀錄且未回報筆數，也未引導使用者改用「封存」。

- **錯誤訊息**：無錯誤例外，回傳僅含 `removed_jobs` 與 `moved_to`
- **重現步驟**：對已有測驗作答紀錄的課程呼叫 `CourseSettingsService.delete_course`
- **影響範圍**：`services/course_settings.py`、HTTP/MCP 刪除課程端點與學習紀錄完整性

## 2. 根本原因

系統尚未區分「封存（archived）」與「刪除」，舊學期或結束課程只能刪除而造成學習紀錄缺口。

## 3. 修正或規避方式

已先於進入 Phase 1 前補強刪除保護（`CourseSettingsService.delete_course`、HTTP `DELETE /api/courses/{code}`、MCP `delete_course`、UI `courseActionsHtml`），採用 Google Classroom 模式：僅 `status == archived` 可刪除，未封存回報錯誤/409/confirm_warning；刪除僅移除資料庫紀錄（含 8 張學習紀錄表）並回傳 `learning_records_removed`，`study/` 內任何檔案不搬不刪（僅舊佈局 `output/courses/<code>` 移入 `deleted/`）。Phase 2（Task 11）已實作 `CourseLifecycleService.archive`/`restore`、`QueueRepository` 封存排除與 `StudyPlanService.get_today`/`due_reviews` 封存隱藏；Phase 3（Task 13）已接上 HTTP（`POST /api/courses/{code}/archive`、`/restore`）、MCP（`set_course_archived`）與網頁「封存／恢復」及未封存停用刪除按鈕。（Refs: ISSUE-065）

## 4. 防回歸

- `tests/test_course_lifecycle.py::CourseDeletionRulesTests`：`test_delete_refused_unless_archived`、`test_delete_archived_course_keeps_study_files`、`test_delete_archived_course_moves_only_legacy_output`
- `tests/test_course_lifecycle.py::CourseArchiveAndRenameTests`：`test_archive_excludes_queue_today_and_due_reviews_and_restore_reinstates`
- `tests/test_study_library_api.py::StudyLibraryApiAndMcpTests`：HTTP `/archive`、`/restore` 與 MCP `set_course_archived`、`confirm=False` 掃描測試

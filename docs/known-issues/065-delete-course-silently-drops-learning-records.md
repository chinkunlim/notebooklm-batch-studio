# ISSUE-065：刪除課程直接移除資料庫學習紀錄且未建議封存

- **狀態**：🔴 未解決 (Open)
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

計畫於 Task 5（courses.status）與 Task 11（CourseLifecycleService.archive/restore、刪除回報 lost records）修正。（相關程式碼註解加 `Refs: ISSUE-065`）

## 4. 防回歸

待補：tests/test_course_lifecycle.py (Task 5/11)

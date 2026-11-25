# ISSUE-058：課程代碼三規則不一致：CP__30000 解析碰撞為 CP

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 現象

services/course_parser.py::parse_course_folder_name('CP__30000-團體諮商') 回傳 ('CP', '30000-團體諮商')，導致所有同系所課程代碼碰撞成 CP 而互相覆蓋，且與學期前綴及 <學期>_<課號> 規則不一致。

- **錯誤訊息**：無錯誤例外，直接回傳碰撞代碼 `('CP', '30000-團體諮商')`
- **重現步驟**：呼叫 `parse_course_folder_name('CP__30000-團體諮商')` 與 `parse_course_folder_name('CP__31000-生涯諮商與實務')`
- **影響範圍**：所有同系所 `CP__*` / `GC__*` / `YY__*` 課程與跨學期重修課程

## 2. 根本原因

舊解析正則把雙底線 __ 視為一般分隔符並只取前段 CP，未整合學期與校方課號規則。

## 3. 修正或規避方式

已於 `c480aba`（新增 `domain/course_identity.py` 解析校方 `__`/`_` 課號並組合 `<學期>_<課號>`）、`01e523d`（切換 `StudyLibraryService` 使用新解析器）、`28749bb`（安全改代碼）與 `b2178d1`（`consolidate` 整併舊代碼與資料夾名）修正。（`Refs: ISSUE-058`）

## 4. 防回歸

- `tests/test_course_identity.py`（`test_parses_school_course_folders`、`test_non_course_folders`、`test_codes`）
- `tests/test_study_library.py::test_real_school_folder_names_yield_distinct_codes`
- `tests/test_course_lifecycle.py::CourseArchiveAndRenameTests`

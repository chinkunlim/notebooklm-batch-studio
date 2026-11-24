# ISSUE-058：課程代碼三規則不一致：CP__30000 解析碰撞為 CP

- **狀態**：🔴 未解決 (Open)
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

計畫於 Task 2（domain/course_identity.py）、Task 11（安全改代碼）與 Task 16（現有資料整併）修正。（相關程式碼註解加 `Refs: ISSUE-058`）

## 4. 防回歸

待補：tests/test_course_identity.py 與 tests/test_study_library.py

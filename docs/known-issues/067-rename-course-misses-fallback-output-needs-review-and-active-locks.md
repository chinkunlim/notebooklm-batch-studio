# ISSUE-067：課程改代碼遺漏舊輸出、needs_review、筆記 stitched_path 與執行中保護

- **狀態**：🟢 已解決 (Resolved)
- **發現日期**：2026-11-25
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 現象

在暫存 `DATA_DIR` 將課程代碼 `115-1` 改名為 `115-1_CP31000` 後，舊輸出資料夾、`needs_review` 隔離資料夾與筆記狀態內的 `stitched_path` 未跟著搬移／改寫，且若筆記或文獻背景任務正在執行也未被攔截：

- **錯誤訊息**：
  ```text
  output/courses/<old> still there: True | <new> exists: False
  needs_review <old>_* still there: True
  state stitched_path: 115-1/ch01_t_學習筆記.md | exists: False
  ```
- **重現步驟**：建立沒有 `study_dir` 的課程並於 `output/courses/<old>`、`needs_review/<old>_*` 與筆記狀態 `stitched_path` 寫入舊代碼路徑後呼叫 `CourseLifecycleService.rename(..., dry_run=False)`
- **影響範圍**：`services/course_lifecycle.py`、`adapters/db/course_identity_repo.py`、`entrypoints/http/artifacts.py`（`_needs_review/<new>_...` 下載路徑）

## 2. 根本原因

Task 11 初版設計改代碼時只盤點了 11 張資料庫表與 `course.toml` / `notes_state` / `scratch/notes` / `QA_Notes` 四類檔案，未完整盤點整個 `DATA_DIR` 下所有以 `course_code` 命名的目錄（無 `study_dir` 時的後備 `output/courses/<old>/`、`needs_review/<old>_*`）與筆記狀態內的 `stitched_path`，且只檢查 `artifact_jobs` 的 `running` 狀態而漏掉筆記生成狀態與 `literature_job.lock` 鎖定檢查。

## 3. 修正或規避方式

補齊 `course_lifecycle` / `course_identity_repo` 的後備輸出搬移、`needs_review/<old>_*` 改名並更新 `artifact_jobs.output_file` 前綴、改寫指向 `scratch/notes/<old>/` 的 `stitched_path`（不動 `study_dir` 路徑）、納入 dry-run 與失敗回滾，並阻擋筆記 `running` 狀態或持鎖文獻任務期間之改代碼（Refs: ISSUE-067）。

## 4. 防回歸

- `tests/test_course_lifecycle.py::CourseArchiveAndRenameTests`：
  - `test_rename_moves_fallback_output_and_needs_review_and_serves_http_200`
  - `test_rename_rewrites_scratch_stitched_path_but_keeps_study_dir_path`
  - `test_rename_refused_during_note_generation_or_locked_literature_run`
  - `test_rename_midway_failure_rolls_back_fallback_output_and_needs_review`

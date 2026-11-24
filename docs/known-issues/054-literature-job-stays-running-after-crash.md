# ISSUE-054：伺服器中斷後文獻工作紀錄永遠停在 running

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-029`（發現）、`TASK-032`（修復）

## 1. 現象

literature_jobs 在背景工作執行中伺服器被關閉時，資料列維持 state=running、finished_at 為空；重啟後 latest_job() 仍回傳這筆 running。literature-fetch 曾以 ISSUE-005 修正（新 runner 啟動時把殘留工作標為 failed），本專案未移植。

- **錯誤訊息**：見上方現象描述
- **重現步驟**：見上方現象描述
- **影響範圍**：見上方現象描述

## 2. 根本原因

LiteratureJobRunner 的執行狀態只存在記憶體，啟動時沒有清理資料庫中殘留的 running 工作。

## 3. 修正或規避方式

已於 `TASK-032` 移植 `literature-fetch ISSUE-005` 修復機制：
- `adapters/db/literature_repository.py::close_stale_jobs` 與 `services/literature/protocols.py`：批次將資料庫殘留的 `state=running` 工作更新為 `state=failed`、寫入失敗原因與 `finished_at`。
- `services/literature/jobs.py::LiteratureJobRunner`：在 `__init__` 呼叫 `_close_stale_on_startup()` 自動清理前次中斷殘留的工作；`_run_worker()` 改為捕捉 `BaseException` 以確保中斷訊號也會標記 `JobState.FAILED`（Refs: `ISSUE-054`）。

## 4. 防回歸

`tests/literature/test_stale_jobs.py::StaleJobTest`（含 `test_new_runner_closes_jobs_and_steps_left_by_a_stopped_process` 與 `test_worker_base_exception_marks_job_failed`）。

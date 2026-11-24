# ISSUE-057：LiteratureJobRunner 啟動清理未檢查程序鎖，會誤殺另一程序進行中的文獻工作

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **來源**：[ISSUE-054](054-literature-job-stays-running-after-crash.md) 修正（commit `13dff45` / `TASK-032`）引起之回歸問題
- **Agent**：`antigravity`
- **任務**：`TASK-034`

## 1. 現象

網頁伺服器（`entrypoints/api.py:347`）與 MCP stdio 伺服器（`entrypoints/mcp_extensions.py:69-92`）為不同 OS 程序，各自於啟動時建立 `LiteratureJobRunner`。當網頁程序正在背景下載文獻（資料庫有一筆 `state=running` 工作）時，若此時 Claude Code／Antigravity 啟動 MCP stdio 連線建立第二個 `LiteratureJobRunner`，`_close_stale_on_startup()` 會把資料庫中所有 `running` 工作標記為 `failed`，誤殺仍在執行的網頁程序工作。

- **錯誤訊息**：`前次程序已中斷，工作未完成`（實際上該工作仍在另一程序執行）
- **重現步驟**：
  1. 程序 A 建立 `LiteratureRepository(session).start_job("download", total=10)` 或透過 `runner1.start("download")` 啟動進行中文獻工作。
  2. 程序 B 建立第二個 `LiteratureJobRunner(scope)`。
  3. 查詢資料庫 `latest_job().state` 由 `JobState.RUNNING` 被誤改為 `JobState.FAILED`。
- **影響範圍**：同時執行 Web 伺服器與 MCP stdio 代理程序時的 `literature_jobs` 狀態追蹤。

## 2. 根本原因

`TASK-032`（`ISSUE-054`）僅移植了 `literature-fetch ISSUE-005` 的啟動關閉殘留 `running` 工作邏輯（`jobs.py:52-72`），漏移植 `literature-fetch` 用於跨程序互斥與判斷活體持有者的 `fcntl.flock` 程序鎖 `RunLock`（原 `adapters/locks.py`），導致第二個程序無法區分「前次程序已崩潰留下的僵屍工作」與「另一個活著的程序正在執行的工作」。

## 3. 修正或規避方式

已於 `TASK-034` 移植 `literature-fetch` `RunLock` 並接線至所有文獻工作執行器（Refs: `ISSUE-057`）：
- `config/settings.py`：新增 `literature_job_lock_path` 屬性（`<data_dir>/state/literature_job.lock`），鎖檔路徑集中由 config 層提供。
- `adapters/locks.py`：移植 `RunLock`（使用 `fcntl.flock(..., LOCK_EX | LOCK_NB)`），重疊取得時拋出 `AlreadyRunningError`。
- `services/literature/protocols.py` & `adapters/literature/factory.py`：在 `LiteratureRuntimeProtocol` 定義 `open_run_lock(path)`，由 `AdapterLiteratureRuntime` 回傳 `RunLock(path)`（維持單向分層 `services -> config`、透過 protocol 呼叫 adapter）。
- `services/literature/jobs.py::LiteratureJobRunner`：
  - `start()` 於建立 `running` 資料庫列前先同步取得 `run_lock`，工作執行期間持續持有鎖，`_run_worker()` 的 `finally` 區塊（含正常結束、例外、`BaseException`）必先釋放鎖再清狀態與通知 `on_done`。
  - `_close_stale_on_startup()` 先透過 `_close_stale_in_manager()` 嘗試取得 `run_lock`；**只有成功取得鎖才呼叫 `close_stale_jobs()`**，若另一程序持有鎖則捕捉 `AlreadyRunningError` 跳過清理。
- `entrypoints/api.py`（`create_app`）與 `entrypoints/mcp_extensions.py`（`_literature_runner`）：皆注入 `lock_path=cfg.literature_job_lock_path` 與 `lock_factory=RunLock`。

## 4. 防回歸

- `tests/literature/test_locks.py::RunLockTest`
- `tests/literature/test_stale_jobs.py::StaleJobTest::{test_second_runner_does_not_close_a_job_owned_by_a_live_runner,test_job_left_running_without_lock_holder_is_closed}`

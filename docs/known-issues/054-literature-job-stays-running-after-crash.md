# ISSUE-054：伺服器中斷後文獻工作紀錄永遠停在 running

- **狀態**：🔴 未解決 (Open)
- **發現日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-029`

## 1. 現象

literature_jobs 在背景工作執行中伺服器被關閉時，資料列維持 state=running、finished_at 為空；重啟後 latest_job() 仍回傳這筆 running。literature-fetch 曾以 ISSUE-005 修正（新 runner 啟動時把殘留工作標為 failed），本專案未移植。

- **錯誤訊息**：見上方現象描述
- **重現步驟**：見上方現象描述
- **影響範圍**：見上方現象描述

## 2. 根本原因

LiteratureJobRunner 的執行狀態只存在記憶體，啟動時沒有清理資料庫中殘留的 running 工作。

## 3. 修正或規避方式

待辦（交由 Antigravity）：比照 literature-fetch ISSUE-005 與其 test_web.py::test_new_runner_closes_jobs_and_steps_left_by_a_stopped_process，在 runner 建立或 web 啟動時把殘留 running 工作標為 failed。（相關程式碼註解加 `Refs: ISSUE-054`）

## 4. 防回歸

移植上述測試。

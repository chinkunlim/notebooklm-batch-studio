# ISSUE-002：題數不足的測驗被標成 DONE 而非 NEEDS_REVIEW

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-007`

## 1. 現象

湊不滿 30 題的測驗已隔離到 needs_review/，但工作狀態是 DONE，總覽報告看不到需審查警告

- **錯誤訊息**：log 有 `Quiz incomplete (N questions), quarantined to ...`，但工作狀態為 `done`
- **重現步驟**：NotebookLM 三次產出合併去重後不足 30 題 → 查看該工作狀態
- **影響範圍**：`summary.md` / `summary.html` 的「需審查」標記永遠不出現；進度百分比把不合格測驗算成完成

## 2. 根本原因

`ArtifactRunner._process_quiz` 隔離不足題數的測驗後，跟成功時一樣「回傳檔案路徑」。
`WorkerPool._process_job` 只要 executor 有回傳就呼叫 `complete_job`（狀態 DONE），
整個程式沒有任何地方會把 `JobStatus.NEEDS_REVIEW` 寫入資料庫。

## 3. 修正或規避方式

- 新增領域例外 `NeedsReviewError(message, output_file)`；`_process_quiz` 題數不足時拋出它。
- `WorkerPool` 捕捉後呼叫新的 `QueueRepository.mark_needs_review`：狀態設為 `needs_review`、保留隔離檔路徑、**不自動重試**。
- 使用者可用既有的 retry（網頁、MCP `retry_item`）把它改回 PENDING。網頁的狀態徽章也加上警示色。

## 4. 防回歸

`tests/test_needs_review_and_ollama.py`：`NeedsReviewTest.test_worker_marks_job_needs_review`、
`NeedsReviewTest.test_retry_resets_needs_review_job`；`tests/test_services_and_cli.py` 的 quiz 隔離斷言改為預期 `NeedsReviewError`。

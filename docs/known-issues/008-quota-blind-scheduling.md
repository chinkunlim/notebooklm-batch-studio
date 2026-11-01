# ISSUE-008：排程不看即時額度，預估天數用猜的

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-008`

## 1. 現象

- 工作被認領後一律直接送出生成請求，即使額度表已顯示該動作額度不足，等 NotebookLM 拒絕才進 QUOTA_WAIT，白白浪費一次請求。
- 新增課程預覽的「約 N 天」固定用「每天 100 個工作」估算；任務數也寫死成「每講 6 項 + 2」，full profile 實際是每講 8 項 + 2。
- 每次進 QUOTA_WAIT 都吃掉一次重試次數（最多 3 次），等過幾次額度後一個真正的錯誤就會直接變 FAILED。

- **錯誤訊息**：無
- **重現步驟**：額度接近用完時跑 batch；或在網頁預覽新增 6 講的課程（顯示 38 項，實際 50 項）
- **影響範圍**：`services/orchestrator.py`（`execute_job`、`preview_course_folders`）、`adapters/db/repository.py`（`block_job_quota`）、網頁預覽

## 2. 根本原因

`client.settings.get_usage()` 會回報每種動作的 `has_sufficient_quota` 與 `estimated_cost_percent`（以 5 小時額度窗的百分比計），但程式只在顯示額度時讀它，排程與預估都沒用到。
`claim_next_job` 認領時把 `attempts` 加一，`block_job_quota` 沒有還回去。

## 3. 修正或規避方式

- 新增 `services/quota_planner.py`：把產出類型對應到額度表的動作種類。
- `execute_job` 開始前先讀額度表，該動作額度不足就直接拋 `QuotaExceededError`，等到擋住它的額度窗重置時間；讀不到額度表時照常執行（不讓輔助功能擋住工作）。
- 預覽改成 async，用 `generate_jobs_for_course` 算出真正的任務清單，再用即時花費估算總用量、需要幾個 5 小時窗與等待時數；讀不到額度時明確標示「未估算」。
- `block_job_quota` 把認領時加的 `attempts` 還回去。

## 4. 防回歸

`tests/test_remaining_fixes.py`：`QuotaPlannerTest`、`QuotaPrecheckTest`、`PreviewEstimateTest`。

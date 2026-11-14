# ISSUE-038：生成失敗的任務在網頁無重試按鈕且背景佇列不會自動重試恢復

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-14
- **Agent**：`antigravity`
- **任務**：`TASK-021`

## 1. 現象

產出任務（語音導覽、30 題測驗、心智圖等）在 NotebookLM 產生過程中若失敗成為 `failed`（或單批測驗暫時失敗），使用者在網頁介面看不到任何「重試」按鈕，無法手動 rerun，背景 WorkerPool 也不會自動重試或重新排入恢復。

- **重現步驟**：
  1. 任務執行時遇到暫時性網路/NotebookLM API 錯誤或 PDF 上傳失敗。
  2. 任務失敗 3 次後轉為 `failed`，或因單批測驗錯誤直接失敗。
  3. 打開課程詳情或佇列狀態列，只能看到紅色失敗徽章，無任何「重試 / 全部重試」按鈕，背景探測迴圈亦不會自動恢復。
- **影響範圍**：所有課程產出任務之失敗手動重跑、批次失敗恢復、中斷殘留 `running` 任務復原與 UI/MCP 控制一致性。

## 2. 根本原因

1. **前端 UI 缺乏失敗重試與重整控制**：`studio-batch.js` 的狀態列、`renderActiveJobs` 與 `jobRowHtml` 未對 `failed` / `needs_review` 狀態渲染「重試」或「重新生成」按鈕；`fetchStatus()` 也只在 `pending + running > 0` 時視為運作中，忽略 `failed > 0`。
2. **同步 FastAPI 路由無法取得 Event Loop 啟動佇列**：`entrypoints/http/queue.py` 與 `entrypoints/http/settings.py` 多個控制端點（如 `retry_job`、`start_queue`、`regenerate_artifact`）為同步 `def`，在 Starlette threadpool 中呼叫 `BatchStudioService.start_queue()` 時因無執行中的 asyncio loop 而無法啟動背景 WorkerPool；且單筆重試與重新生成並未喚醒佇列。
3. **重試未歸零嘗試次數與缺乏冷卻自動恢復**：`QueueRepository.retry_job` 未將 `attempts` 歸零（造成手動重試後再次失敗很快耗盡）；暫時性失敗缺乏退避與分輪冷卻（`cooldown_until`），`_quota_probe_loop` 僅喚醒 `QUOTA_WAIT` 而不恢復冷卻期滿的 `FAILED` 任務，`WorkerPool.start()` 亦未復原程序重啟遺留的 `RUNNING` 任務。
4. **PDF 失敗上傳與測驗單批脆弱性**：`_upload_single_lecture` 在講義尚有舊 `source_id` 但 `upload_status == "failed"` 時會誤判為已上傳；`QuizRunner._collect_batches` 在單批失敗時直接中止而不繼續嘗試剩餘批次。

## 3. 修正或規避方式

已在相關模組加上 `Refs: ISSUE-038`：

1. **領域介面與資料庫層**：
   - `domain/repositories.py`、`adapters/db/queue_repository.py`：`claim_next_job` 檢查 `cooldown_until <= now` 並優先領取低嘗試次數任務；`fail_job` 以每輪 `max_attempts=3` 計數並設定 60 秒 `cooldown_until`；`retry_job` 重置 `attempts = 0`；新增 `retry_failed_jobs`（支援課程篩選、`include_needs_review` 與冷卻／9 次上限檢查）與 `recover_running_jobs`。
2. **服務與背景背景恢復層**：
   - `services/worker_pool.py`：啟動時呼叫 `recover_running_jobs()` 復原殘留 `RUNNING` 任務；失敗前加上 `0.2s` 非同步退避；`_quota_probe_loop` 定期呼叫 `retry_failed_jobs(respect_cooldown=True)`（上限 9 次／3 輪）。
   - `services/orchestrator.py`、`services/course_onboarding.py`、`services/quiz_runner.py`：`retry_job` 後自動呼叫 `start_queue()`；新增 `retry_course_failed_jobs`；`start_queue`、`resume_quota_wait` 及講義重上傳均納入 `FAILED` 恢復；`QuizRunner._collect_batches`（透過 `_try_single_quiz_attempt`）於非配額／認證錯誤時記錄警告並繼續剩餘批次。
3. **HTTP、MCP 與 Web UI 一致性（核心規則 13）**：
   - `entrypoints/http/queue.py`、`entrypoints/http/settings.py`：控制路由改為 `async def` 以確保能取得 FastAPI 運行中的 asyncio loop；新增 `POST /api/courses/{code}/jobs/retry-failed`。
   - `entrypoints/mcp_job_prompts.py`：新增 `retry_course_failed_jobs(course_code, include_needs_review=True, confirm=False)` MCP 工具。
   - `entrypoints/static/studio-queue.js`、`studio-batch.js`：實作 `retryJob`、`retryFailedJobs`，於任務列、活躍任務列表、課程狀態列（「重試失敗／需審查項目」）與頂部狀態列完整提供手動重試按鈕，並重建離線 `docs/demo/index.html`。

## 4. 防回歸

- `tests/test_failed_job_rerun.py`：
  - `FailedJobRetryAndRecoveryTest.test_retry_job_resets_attempts_and_cooldown`
  - `FailedJobRetryAndRecoveryTest.test_worker_pool_auto_retries_and_recovers_failed_and_orphans`
  - `FailedJobRetryAndRecoveryTest.test_quiz_runner_survives_transient_batch_failure`
  - `FailedJobHttpAndMcpTest.test_http_and_mcp_retry_failed_endpoints`
- `tests/test_dummy_user_simulation.py`：
  - `UiAndStaticRegressionTest` 驗證前端腳本包含 `retryJob(`、`retryFailedJobs(` 與 `/api/courses/${code}/jobs/retry-failed`。

# ISSUE-035：WorkerPool 記憶體中 blocked_quota_types 未隨 resume 或無 QUOTA_WAIT 任務時清除導致佇列永久卡死

- **狀態**：🔴 未解決 (Open)
- **發現日期**：2026-11-09
- **Agent**：`antigravity`
- **任務**：`TASK-015`

## 1. 現象

當佇列執行期間各類產出物陸續觸發 `QuotaExceededError` 後，`WorkerPool.blocked_quota_types` 記憶體集合會包含所有被擋下的 `ArtifactType`（最多全部 12 種產出物類型）。此時若沒有處於 `quota_wait` 狀態的任務（例如：已刪除原課程並重新加入、手動按「重試」將任務改回 `pending`、或透過 `POST /api/queue/resume` 已經把資料庫中的 `quota_wait` 任務改為 `pending`），佇列看似在執行（`queue_running: true`），但 Worker 完全不會認領任何 `pending` 任務，按「繼續執行」或「立即喚醒等待額度的工作」也無效，必須重啟伺服器重置記憶體狀態才能恢復。

- **錯誤訊息**：無錯誤訊息（Worker 每秒執行 `claim_next_job(worker_id, excluded_types=self.blocked_quota_types)` 皆因所有類型在 `excluded_types` 中而回傳 `None`）
- **重現步驟**：
  1. 執行批次生成時觸發額度限制，使 `self.blocked_quota_types` 加入多個或全部 `ArtifactType`。
  2. 將原課程刪除（或手動 `retry_job`，或呼叫 `/api/queue/resume` 在請求執行緒先將 `QUOTA_WAIT` 改為 `PENDING`），此時資料庫中已無 `status = 'quota_wait'` 的任務。
  3. 新增課程或等待 `PENDING` 任務執行，並點擊「啟動批次生成」或「繼續執行 / 立即喚醒等待額度的工作」。
  4. 觀察佇列：所有 `PENDING` 任務永遠停留在排隊中，不會進入 `RUNNING`。
- **影響範圍**：
  - `src/notebooklm_batch_studio/services/worker_pool.py`（`WorkerPool.resume`、`WorkerPool._quota_probe_loop`）
  - `src/notebooklm_batch_studio/services/orchestrator.py`（`BatchStudioService.resume_queue`、`start_queue`、`resume_quota_wait`、`retry_job`）
  - `src/notebooklm_batch_studio/adapters/db/repository.py`（`QueueRepository.refresh_quota_wait`）

## 2. 根本原因

1. **`blocked_quota_types` 唯一的清除條件過於嚴苛且與 DB 狀態脫鉤**：
   - 在 `worker_pool.py` 中，整個程式唯一呼叫 `self.blocked_quota_types.clear()` 的地方在 `_quota_probe_loop()` 第 327–329 行：
     ```python
     awakened = repo.refresh_quota_wait()
     if awakened > 0:
         self.blocked_quota_types.clear()
     ```
   - 一旦資料庫中已經沒有 `status == 'quota_wait'` 的任務（例如：課程被刪除、任務被單獨重試回 `pending`、或已被 `POST /api/queue/resume` 呼叫 `service.resume_quota_wait()` 提早改回 `pending`），`_quota_probe_loop()` 每次查到的 `awakened` 恆為 `0`，導致 `self.blocked_quota_types` 永遠無法透過 probe loop 清空。
2. **`WorkerPool.resume()` 未清除 `blocked_quota_types`**：
   - `WorkerPool.resume()` 僅設定 `self._paused = False`，完全沒有清空 `self.blocked_quota_types`。
   - 此外，`POST /api/queue/resume` 先呼叫 `service.resume_quota_wait()` 將 DB 的 `quota_wait` 改為 `pending`，再呼叫 `service.resume_queue()`；這反而讓背景 `_quota_probe_loop()` 下次檢查時看到 `0` 筆 `quota_wait`，徹底失去觸發 `awakened > 0` 的機會。
3. **手動喚醒 `resume_quota_wait()` 受限於 `cooldown_until <= now`**：
   - `QueueRepository.refresh_quota_wait()` 預設帶有 `WHERE cooldown_until <= now` 條件，使用者在網頁按「立即喚醒等待額度的工作」時，若 1 小時冷卻時間尚未到，連 DB 中的 `quota_wait` 任務也不會被喚醒。

## 3. 修正或規避方式

1. **`WorkerPool.resume()` 同步清空 `blocked_quota_types`**：
   - 在 `WorkerPool.resume()` 中呼叫 `self.blocked_quota_types.clear()`，確保每次恢復／啟動／喚醒佇列時重置記憶體封鎖集合。
2. **`WorkerPool._quota_probe_loop()` 與 DB 實際 `quota_wait` 狀態對齊**：
   - 在 `_quota_probe_loop()` 中，除了 `awakened > 0` 時清空 `self.blocked_quota_types` 外，若 `self.blocked_quota_types` 非空，查詢目前資料庫中仍處於 `QUOTA_WAIT` 的 `artifact_type` 集合（或檢查 `QUOTA_WAIT` 任務數為 0），將已無任何 `QUOTA_WAIT` 任務的類型從 `self.blocked_quota_types` 移除。
3. **手動喚醒與單筆重試同步解除封鎖**：
   - `QueueRepository.refresh_quota_wait(artifact_type=None, force: bool = False)` 支援 `force=True`（忽略 `cooldown_until <= now`），供使用者手動點擊「立即喚醒等待額度的工作」（`service.resume_quota_wait()`）時強制喚醒所有 `QUOTA_WAIT` 任務並清空 `worker_pool.blocked_quota_types`。
   - `BatchStudioService.retry_job(job_id)` 重試單筆任務時，同步將該任務的 `artifact_type` 從 `worker_pool.blocked_quota_types` 移除並確保佇列啟動。
   - 相關程式碼註解加 `Refs: ISSUE-035`。

## 4. 防回歸

- 單元測試（`tests/test_worker_pool.py` / `tests/test_queue_http.py`）：
  1. 測試 `blocked_quota_types` 包含全部 12 種產出物類型且 DB 無 `QUOTA_WAIT` 任務時，呼叫 `resume()` 或經過一次 `_quota_probe_loop()` 後，`blocked_quota_types` 被清空且 `PENDING` 任務能被正常認領執行。
  2. 測試 `POST /api/queue/resume` 能強制喚醒冷卻期內的 `QUOTA_WAIT` 任務並清空 `worker_pool.blocked_quota_types`。

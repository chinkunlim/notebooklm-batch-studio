# ISSUE-005：配額拒絕以 failed 狀態回傳時未被偵測

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-008`

## 1. 現象

generate 回傳 USER_DISPLAYABLE_ERROR 的 failed 狀態而非例外，程式未檢查，未進 QUOTA_WAIT；冷卻固定猜 1 小時

- **錯誤訊息**：無；工作被當成完成或一般錯誤，而不是 `quota_wait`
- **重現步驟**：額度用完後再送出產生請求
- **影響範圍**：配額保護、冷卻時間、續跑

## 2. 根本原因

NotebookLM 拒絕請求時，`generate_*` 常回傳 `GenerationStatus(status="failed", error_code="USER_DISPLAYABLE_ERROR")`
而非拋出 `RateLimitError`。adapter 只用例外判斷配額，沒檢查回傳狀態，於是繼續去下載（拿到舊檔或失敗）。
另外冷卻時間一律猜 3600 秒，但 NotebookLM 實際是「5 小時窗」與「每週窗」，各有 `resets_at`。

## 3. 修正或規避方式

- `finish_generation` 檢查 `is_rate_limited` → `QuotaExceededError`，`is_failed` → `StudioError`，等待後再檢查一次。
- `_translate_errors` 遇到配額錯誤時讀 `client.settings.get_usage()`，用已耗盡視窗中最晚的 `resets_at` 設定冷卻秒數
  （`adapters/notebooklm/quota.py` 的 `retry_after_from_usage`），讀不到才退回 3600 秒。
- 新增 `GET /api/notebooklm/quota`、MCP `get_notebooklm_quota`、網頁額度徽章。
- 建立筆記本前檢查 `get_account_limits().source_limit`，講次超過上限時拋 `SourceLimitExceededError`，不會上傳到一半失敗。

## 4. 防回歸

`tests/test_notebooklm_generation.py`：`test_rate_limited_status_raises_quota_with_reset_time`、`RetryAfterFromUsageTest`；
`tests/test_quota_and_limits.py`：`test_setup_refuses_course_over_source_limit_before_any_upload`、`test_http_and_mcp_expose_quota`。

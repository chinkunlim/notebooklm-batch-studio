# ISSUE-023：網頁用久了出現 Failed to fetch（資料庫連線耗盡）

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

網頁開一段時間（尤其課程頁每 15 秒自動更新、學習專區連續操作）後，按鈕回應「Failed to fetch」或一直轉圈，伺服器 log 出現連線池耗盡。

- **錯誤訊息**：`sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00`
- **重現步驟**：短時間內送出數十個 API 請求
- **影響範圍**：`entrypoints/api.py`（所有 HTTP 路由）

## 2. 根本原因

`scoped_session` 預設以「執行緒」為範圍；FastAPI 把同步路由放在執行緒池執行，每個工作執行緒各自保留一個 session 與一條資料庫連線，請求結束後從不釋放。執行緒數超過連線池上限（5 + 10）後，新請求等 30 秒逾時。

## 3. 修正或規避方式

session 改以「請求」為範圍：`ContextVar` 當 scopefunc，`DbSessionScopeMiddleware` 為每個請求設定新範圍，結束時對所有 registry 呼叫 `remove()` 歸還連線。背景工作（佇列 worker）使用固定的 background 範圍。

## 4. 防回歸

`tests/test_study_plan.py`：`SessionLeakTest`（60 個請求後 `engine.pool.checkedout() == 0`）。

# ISSUE-015：CLI 測試讀寫真實資料庫

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

`test_cli_status`、`test_cli_resume` 會讀寫 `DATA_DIR/db/app.db`。新增 DB 欄位但還沒升級真實資料庫時，這兩個測試就失敗；`resume` 測試還會改動真實佇列。

- **錯誤訊息**：`sqlite3.OperationalError: no such column: artifact_jobs.version`
- **重現步驟**：新增 ORM 欄位後、執行 `alembic upgrade` 前跑測試
- **影響範圍**：`tests/test_services_and_cli.py`

## 2. 根本原因

測試直接呼叫 `main(["status"])`，CLI 內的 `load_config()` 讀 `.env`，指向真實資料庫。

## 3. 修正或規避方式

`TestCliCommands.setUp` 建立暫存 SQLite（`Base.metadata.create_all`），並 patch `cli.load_config` 回傳指向它的設定。

## 4. 防回歸

測試本身：在未升級的真實資料庫下仍全部通過。

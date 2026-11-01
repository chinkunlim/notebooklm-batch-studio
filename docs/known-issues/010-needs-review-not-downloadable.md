# ISSUE-010：needs_review 的檔案在網頁上無法下載

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-008`

## 1. 現象

工作被標成 NEEDS_REVIEW 後，網頁上點它的檔案會 404，使用者無法打開不完整的測驗來審查。

- **錯誤訊息**：`404 Requested file not found`
- **重現步驟**：讓一份測驗湊不滿 30 題，在網頁上點該工作的檔案
- **影響範圍**：`services/orchestrator.py` `_format_jobs_data`、`entrypoints/http/artifacts.py` `download_artifact`

## 2. 根本原因

隔離檔放在 `DATA_DIR/needs_review/`，不在課程產出資料夾內；`_format_jobs_data` 只回傳檔名，下載路由也只在課程產出資料夾內找檔案。

## 3. 修正或規避方式

- `_format_jobs_data` 對 `needs_review/` 底下的檔案回傳 `_needs_review/<資料夾>/<檔名>`。
- 下載路由認得 `_needs_review/` 前綴，只允許資料夾名稱以該課程代碼開頭的檔案，並檢查路徑穿越。
- 課程產出路徑的穿越檢查從字串 `startswith` 改成 `Path.is_relative_to`，避免 `BIO101` 誤放行 `BIO1010` 這類前綴相同的資料夾。

## 4. 防回歸

`tests/test_remaining_fixes.py`：`ReviewDownloadTest`。

# ISSUE-078：DATA_DIR 不在家目錄時，資料夾瀏覽器打不開「學習資料庫」捷徑

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-26
- **Agent**：`claude-code`
- **任務**：`TASK-036`

## 1. 現象

2026-11-26 在隔離測試環境（DATA_DIR 在 /private/tmp）實測加入課程精靈：點「學習資料庫 (study)」顯示「無法開啟：Folder not available」。使用者目前 DATA_DIR 在家目錄下，所以實際沒遇到；若 DATA_DIR 放外接硬碟就會發生。

- **錯誤訊息**：「無法開啟：Folder not available: <DATA_DIR>/study」
- **重現步驟**：DATA_DIR 設在家目錄以外 → 批次排程 → 加入課程 → 點「學習資料庫 (study)」
- **影響範圍**：只有 DATA_DIR 在家目錄外時；使用者目前不受影響

## 2. 根本原因

folder_browser.browse_folders 只允許家目錄底下的路徑，但第一個捷徑就是 config.study_root_dir。

## 3. 修正或規避方式

允許的根目錄加入 study_root_dir 與 scratch_dir（其餘家目錄外的路徑仍拒絕，例如 DATA_DIR 本身、db/）；「上一層」停在最接近的允許根目錄。（相關程式碼註解加 `Refs: ISSUE-078`）

## 4. 防回歸

tests/test_folder_browser_data_roots.py

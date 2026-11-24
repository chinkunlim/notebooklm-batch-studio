# ISSUE-063：config 與 entrypoints 以外存在隱式 load_config() 後備與寫死 DATA_DIR 子路徑

- **狀態**：🔴 未解決 (Open)
- **發現日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 現象

adapters/ 與 services/ 有 8 處 load_config() 後備呼叫與 9 處寫死 data_dir / '...' 子路徑（含 state/gemini_profile、logs 等），測試或執行期容易漏傳設定而讀寫真實資料。

- **錯誤訊息**：無錯誤例外，呼叫端省略 `config` 時會隱式讀取專案 `.env`
- **重現步驟**：`grep -rn "load_config(" src/notebooklm_batch_studio/` 與 `grep -rnE "(data_dir|state_dir|scratch_dir|output_dir|input_dir)\s*/\s*\"" src/`
- **影響範圍**：`adapters/`、`services/` 及單元測試隔離性

## 2. 根本原因

各服務與轉接器為了省略參數而各自預設呼叫 load_config()，且新增路徑屬性未集中於 AppConfig。

## 3. 修正或規避方式

計畫於 Task 4 集中路徑至 config/settings.py 並移除 entrypoints/config 以外所有 load_config() 後備。（相關程式碼註解加 `Refs: ISSUE-063`）

## 4. 防回歸

待補：tests/test_settings_paths.py (Task 4)

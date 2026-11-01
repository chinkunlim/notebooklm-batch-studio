# ISSUE-004：下載與改名可能對到別的講次或未完成的產出

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-008`

## 1. 現象

下載未帶 artifact_id、多數類型未等完成就下載、改名取最新一份、download_audio 下載兩次

- **錯誤訊息**：無（靜默）；可能下載失敗、拿到舊檔或別講次的產出
- **重現步驟**：2 個 worker 同時處理不同講次的同類產出；或產生語音後立刻下載
- **影響範圍**：所有產出類型的下載與 NotebookLM 上的改名

## 2. 根本原因

1. download 不帶 `artifact_id`，函式庫取該類型最新的一份；改名用 `find_latest_artifact` 取整本最新且忽略類型。
2. 語音、投影片、資訊圖表、資料表、影片、讀書指南、心智圖產生後沒有 `wait_for_completion` 就下載。
3. `download_audio` 內有重複區塊：下載兩次，第二次不帶 `artifact_id`，會覆蓋第一次的結果。
4. 讀書指南（STUDY_GUIDE）呼叫 `generate_report` 時沒傳 `report_format`，實際產生的是 briefing doc。

## 3. 修正或規避方式

見 ADR-004：generate 等完成並回傳 artifact id，download / rename 一律帶 id；`download_*` 合併為 `download_artifact()`
（只下載一次）；STUDY_GUIDE 傳 `report_format="study_guide"`。

## 4. 防回歸

`tests/test_notebooklm_generation.py`：`test_download_audio_downloads_once_by_artifact_id`、
`test_audio_download_and_rename_target_generated_artifact`、`test_study_guide_requests_study_guide_format`、
`test_quiz_variants_map_to_difficulty_and_download_by_id`、`test_failed_after_wait_raises`。

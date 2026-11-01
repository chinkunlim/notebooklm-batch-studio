# ISSUE-020：網頁課程卡片與學習專區閃卡讀錯欄位／路徑

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

- 首頁課程卡片顯示「undefined 份講義 PDF」「生成進度 0 / 0、0%」，實際有 6 講、57 項完成。
- 學習專區的 3D 抽認卡一律顯示「尚未生成或無法解析」，實際每講都有閃卡。

- **錯誤訊息**：無
- **重現步驟**：有完成產出的課程 → 首頁看卡片；學習專區 → 3D 抽認卡
- **影響範圍**：`entrypoints/static/index.html` `fetchCourses`、`services/study_service.py` `get_lecture_flashcards`

## 2. 根本原因

- 卡片讀 `c.stats`、`c.lectures_count`，但 `GET /api/courses` 回傳的是 `counts`、`total_jobs`、`lecture_count`。
- 閃卡用「檔名含講次」的 glob 找檔案，但檔案實際是 `<NN>_<主題>/flashcards.json`，講次在資料夾名稱。

## 3. 修正或規避方式

卡片改讀正確欄位並顯示等待額度／需審查；閃卡改在 `<NN>_*` 資料夾找 `flashcards*.json`，取最新版本。

## 4. 防回歸

`tests/test_guides_and_reports.py`：`test_finds_lecture_folder_and_newest_version`；卡片以瀏覽器驗證。

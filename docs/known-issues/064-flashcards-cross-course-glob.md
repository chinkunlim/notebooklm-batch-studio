# ISSUE-064：閃卡後備搜尋跨課程 glob 可能讀到別門課的閃卡

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 現象

services/study_service.py:210-213 當舊路徑找不到閃卡時，會執行 study_root_dir.glob('*/*/03 Notes/NotebookLM/<NN>_*/flashcards*.json')，同講次編號會讀到其他課程的閃卡。

- **錯誤訊息**：無錯誤例外，查詢 A 課程某講次閃卡時可能回傳 B 課程同講次的閃卡
- **重現步驟**：在 `study/` 下兩門課皆有 `03 Notes/NotebookLM/03_*/flashcards.json` 且無舊 `output/courses/` 時呼叫 `get_lecture_flashcards`
- **影響範圍**：`services/study_service.py::get_lecture_flashcards`

## 2. 根本原因

StudyTrackerService 未查詢課程的 study_dir，便用雙層萬用字元掃描整個 study 樹。

## 3. 修正或規避方式

已於 `5770358`（`services/study_service.py`）移除跨課程 glob 搜尋，改為嚴格依該課程自身的 `study_dir`／輸出根目錄解析閃卡檔案。（`Refs: ISSUE-064`）

## 4. 防回歸

- `tests/test_old_layout_retired.py::test_flashcards_never_read_another_course`

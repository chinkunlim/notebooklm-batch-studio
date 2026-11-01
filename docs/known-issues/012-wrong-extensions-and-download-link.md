# ISSUE-012：投影片與資料表副檔名錯誤，網頁下載連結忽略 rel_path

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

- 投影片實際下載的是 PDF，卻存成 `slide_deck.md`；資料表下載的是 CSV，卻存成 `data_table.md`，開啟會是亂碼或格式錯誤。
- 網頁「生成任務」表格的下載按鈕只用檔名組網址，needs_review 的檔案（`_needs_review/...`）點了會 404。

- **錯誤訊息**：無；下載路由回 404（needs_review 檔）
- **重現步驟**：產生 SLIDE_DECK / DATA_TABLE 後打開本機檔；或在網頁點 needs_review 工作的下載按鈕
- **影響範圍**：`services/artifact_runner.py` `SIMPLE_OUTPUTS`、`entrypoints/static/index.html`

## 2. 根本原因

`SIMPLE_OUTPUTS` 的檔名是早期寫死的 `.md`；notebooklm-py 的 `download_slide_deck` 預設輸出 PDF（可選 pptx），
`download_data_table` 輸出 CSV。網頁表格沒有使用 API 已提供的 `rel_path`。

## 3. 修正或規避方式

- 投影片存成 `.pdf`，課程產出設定選 PPTX 時存 `.pptx` 並傳 `output_format`；資料表存成 `.csv`。
- 網頁下載按鈕改用 `j.rel_path`。

## 4. 防回歸

`tests/test_versions_and_options.py`：`test_slide_deck_saved_as_pdf_or_pptx`、`test_data_table_saved_as_csv`。

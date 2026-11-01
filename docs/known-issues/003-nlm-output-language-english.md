# ISSUE-003：NotebookLM 產出語言預設為英文

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-008`

## 1. 現象

語音、投影片、資訊圖表等未傳 language，函式庫預設 en；報告傳了無效代碼 zh-TW

- **錯誤訊息**：無（靜默）；產出的語音旁白為英文
- **重現步驟**：zh-TW 課程跑 audio / infographic / slide_deck / data_table / video / mind_map
- **影響範圍**：所有支援 `language` 的產出；報告傳了無效代碼

## 2. 根本原因

notebooklm-py 的 `generate_audio` 等函式 `language` 參數預設為 `"en"`（只有明確傳 `None` 才讀 `NOTEBOOKLM_HL`）。
adapter 只把「請用繁體中文」寫進 instructions，沒有傳 `language`；instructions 無法改變語音旁白語言。
報告雖有傳，但傳的是 `"zh-TW"`，函式庫的繁體中文代碼是 `"zh_Hant"`（`notebooklm/_app/language.py`）。

## 3. 修正或規避方式

新增 `to_nlm_language()`（`adapters/notebooklm/generation.py`）：`en` → `en`，其餘（zh-TW、bilingual）→ `zh_Hant`，
所有支援 `language` 的 generate 都傳入；runner 一律帶 `course.language`。測驗與閃卡在函式庫沒有 language 參數，仍靠 instructions。

## 4. 防回歸

`tests/test_notebooklm_generation.py`：`test_audio_uses_traditional_chinese_waits_and_returns_artifact_id`、
`test_every_language_aware_generator_passes_zh_hant`、`test_english_course_keeps_english`、
`test_audio_download_and_rename_target_generated_artifact`。

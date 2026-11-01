# ISSUE-016：報告的自訂指示被忽略；概念解說格式在網頁連線被拒絕

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

- 簡報文件、讀書指南、部落格文章三種報告，程式送出的中文指示沒有作用（產出語言正確只是因為另外傳了 `language`）。
- 概念解說報告一律失敗。

- **錯誤訊息**：`Unsupported report format <ReportFormat.CONCEPT_EXPLANATION>; expected one of: briefing_doc, study_guide, blog_post, custom`
- **重現步驟**：產生 REPORTS_CONCEPT；或比對報告內容與 prompt 要求
- **影響範圍**：`adapters/notebooklm/client.py` `generate_report`

## 2. 根本原因

notebooklm-py 只有 CUSTOM 格式會讀 `custom_prompt`，預設格式（briefing / study guide / blog）讀的是 `extra_instructions`，
程式卻一律傳 `custom_prompt`。另外函式庫的網頁連線政策（`WEB_CREATION_POLICY`）關閉了 CONCEPT_EXPLANATION，只有 Android 連線開啟。

## 3. 修正或規避方式

- 預設格式改用 `extra_instructions` 傳指示。
- 概念解說改用 CUSTOM 格式，`custom_prompt` 放入函式庫原本的概念解說指示（`CONCEPT_EXPLANATION_DIRECTIVE`）加上我們的指示。

## 4. 防回歸

`tests/test_notebooklm_generation.py`：`test_report_instructions_and_concept_format`。

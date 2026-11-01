# ISSUE-013：報告的 HTML 頁面只是原始文字

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

`*_interactive.html` 報告頁面把 Markdown 原文放在 `<pre>` 裡，標題、粗體、表格都不會排版；原文若含 `<`、`&` 也沒有跳脫。

- **錯誤訊息**：無
- **重現步驟**：產生任一 REPORTS_* 產出，開啟 `_interactive.html`
- **影響範圍**：`services/artifact_runner.py` `_process_report`

## 2. 根本原因

當初只用字串包了一層 HTML 外框，沒有做 Markdown 轉換與跳脫。

## 3. 修正或規避方式

新增 `services/converters/report_converter.py`：先跳脫原文中的 `&` 與 `<`，再用 `markdown`（tables、sane_lists）轉成 HTML，套用深色與列印樣式。

## 4. 防回歸

`tests/test_guides_and_reports.py`：`test_report_html_renders_markdown_and_escapes_html`、`test_concept_report_uses_concept_format`。

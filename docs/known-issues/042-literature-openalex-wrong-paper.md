# ISSUE-042：OpenAlex 開放取用連結可能指向別篇論文

- **狀態**：🟡 已規避 (Mitigated)
- **來源**：整合自 `literature-fetch`（原 `ISSUE-002`，2026-10-20）
- **任務**：`TASK-025`

## 1. 現象

OpenAlex `locations` 中的倉儲連結（例如 HAL、Dialnet）偶爾會指向完全不同的論文 PDF（例如 Braun & Clarke 2006）。

- **錯誤訊息**：`title mismatch, rejected key=... first_text='...'`
- **影響範圍**：任何透過 OpenAlex 開放取用連結下載的文獻。

## 2. 根本原因

OpenAlex 索引會將引用該文獻的文章或錯誤配對的倉儲紀錄列為該作品的 location。

## 3. 修正或規避方式

下載後以 `pypdf` 讀取前幾頁文字，目標標題中 4 個字母以上的字需有 70% 出現才存檔（`domain/literature/literature.py::title_matches`、`services/literature/literature.py::_acceptable`）。無文字層的掃描檔不阻擋，但記 WARNING。

## 4. 防回歸

`tests/literature/test_literature.py::TitleTest`、`ServiceTest::test_wrong_paper_is_rejected_and_next_source_used`、`ServiceTest::test_unreadable_pdf_text_is_accepted`。

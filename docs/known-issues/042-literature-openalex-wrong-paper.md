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

下載後以 `pypdf` 讀取前幾頁文字，目標標題中 4 個字母以上的字（或中文 bigram）需有 70% 出現才存檔（`src/notebooklm_batch_studio/domain/literature/literature.py:195-220` `title_matches()`、`src/notebooklm_batch_studio/services/literature/literature.py:237-260` `_acceptable()`）。無文字層或中文亂碼的掃描檔不阻擋，但記 WARNING。

> **維持 `Mitigated` 理由**：錯誤來源屬外部 OpenAlex 倉儲索引資料品質問題（無法自上游根治），且無文字層掃描檔依設計放行，故本專案以自動標題驗證並切換下一來源規避之。

## 4. 防回歸

`tests/literature/test_literature.py::TitleTest`（3 測試）、`ServiceTest::test_wrong_paper_is_rejected_and_next_source_used`、`ServiceTest::test_unreadable_pdf_text_is_accepted`、`ServiceTest::test_next_institutional_route_is_tried_after_a_wrong_paper`。

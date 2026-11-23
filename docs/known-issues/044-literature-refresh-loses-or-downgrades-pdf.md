# ISSUE-044：refresh（試抓正式版）會遺失書籍 PDF，或把正式版換成作者稿

- **狀態**：🟢 已根治 (Resolved)
- **來源**：整合自 `literature-fetch`（原 `ISSUE-004`，2026-10-20）
- **任務**：`TASK-025`

## 1. 現象

對已下載書籍執行 `refresh` 且找不到公版掃描檔時，原 PDF 留在 `superseded/` 未放回；對正式版執行 `refresh` 且只找到作者稿時會覆蓋正式版。

## 2. 根本原因

`download_reference()` 在 refresh 時先將舊檔 `set_aside()` 至 `superseded/`，若書籍分支 `_download_book()` 失敗未 `restore()`，或一般文獻分支未檢查 `is_version_of_record`，就會遺失或降級 PDF。

## 3. 修正或規避方式

`_download_book(attempt, aside)` 找不到檔案時改走 `_no_pdf()` 放回舊檔；`download_reference()` 在 refresh 且只找到作者稿／預印本時也放回舊檔（正式版優先原則）。

## 4. 防回歸

`tests/literature/test_books.py::BookFlowTest::test_refreshing_a_book_without_a_better_copy_keeps_its_pdf`、`tests/literature/test_literature.py::ServiceTest::test_refresh_never_replaces_a_file_with_an_author_copy`。

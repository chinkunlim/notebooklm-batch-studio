# ISSUE-072：整本課本檔名與既有章節資料夾不同時會重複建立講次；同名時偵測卡片不出現

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-25
- **Agent**：`claude-code`
- **任務**：`TASK-036`

## 1. 現象

2026-11-25 在暫存資料模擬真實課程（章節已由 02 Handouts 搬到 01 Materials/<課本書名>/，並已上傳）：整本 PDF 檔名與該資料夾不同時，偵測卡片顯示「5 章，0 章已存在」，切割後寫到新資料夾，講次 1–3 各出現兩次（舊的已上傳、新的待上傳）；檔名相同時切割正確，但偵測卡片完全不出現。

- **錯誤訊息**：沒有錯誤。修正前暫存資料的結果：`lectures after: [(1, '…/Research Methods 13e full book/Ch01…', 'pending', None), (1, '…/Research Methods, Design, and Analysis 13th ed/Ch01…', 'uploaded', 'src-1'), …]`
- **重現步驟**：課程的章節已在 `01 Materials/<書名>/`（有 `.textbook.json`）；把整本 PDF 以不同檔名放進 `01 Materials/`，按偵測卡片「預覽並切割」並套用
- **影響範圍**：生涯諮商與實務、心理學研究法（兩門課的章節都是 2026-11-25 從 02 Handouts 搬過去的）。真實資料沒有受影響：發現時使用者還沒放入整本課本

## 2. 根本原因

split_textbook 一律寫到 01 Materials/<PDF 檔名主體>/，只比對該資料夾內的 ChNN 檔；搬移既有章節時資料夾用的是課本書名，和使用者之後放入的 PDF 檔名幾乎不會相同。pending_textbooks 又只看該資料夾有沒有 .textbook.json，有標記就當作已切割，不管是否還缺章節。

## 3. 修正或規避方式

services/textbook_split.py 新增 _chapter_folder：PDF 自己的同名資料夾存在就用它，否則課程只有一個已標記的章節資料夾時改用那一個；pending_textbooks 改為只要還有未建立的章節就列出（無書籤的錯誤只在該 PDF 自己的資料夾未標記時列出）。預覽會顯示輸出資料夾，使用者確認後才寫入。（相關程式碼註解加 `Refs: ISSUE-072`）

## 4. 防回歸

tests/test_textbook_split.py::TextbookServiceTest::test_whole_book_named_like_chapter_folder_is_detected、test_whole_book_with_other_name_fills_the_existing_chapter_folder；tests/test_auto_schedule.py::WebEntrypointsTest::test_pending_textbooks_api_and_web

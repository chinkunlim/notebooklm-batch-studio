# ISSUE-073：課本章節當講次的課，放進一份講義就整個改用講義當講次

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-25
- **Agent**：`claude-code`
- **任務**：`SPEC-025 R4a`

## 1. 現象

生涯諮商與實務、心理學研究法都以 01 Materials/<課本>/ 的章節當講次（02 Handouts 空的）。只要 02 Handouts 出現一份 PDF，watch 或重新加入課程會重新掃描：課本章節講次全部被刪掉、換成那份講義，並排入整套產出工作。2026-11-25 用暫存資料重現：3 個章節講次變成 [(1, week1.pdf)]，佇列新增 10 件工作（會耗額度）。

- **錯誤訊息**：無錯誤。watch 印出「🔔 偵測到新講義檔案：week1.pdf」與「✅ 已新增 10 個產出任務至佇列。」
- **重現步驟**：課程 `01 Materials/Book/` 有 `.textbook.json` 與 Ch01–Ch03，`02 Handouts` 空的 → 掃描並存入資料庫 → 在 `02 Handouts/` 放 `week1.pdf` → 呼叫 `cli._on_pdf_detected`（即 `watch`）→ 講次只剩 week1.pdf
- **影響範圍**：所有以課本章節當講次的課（目前兩門）。觸發途徑：`watch`、網頁／MCP 重新加入同一課程資料夾、`register_course_folder`；切割整本課本後若 `02 Handouts` 有 PDF，新章節也不會加入講次。使用者真實資料未受影響（兩門課的 `02 Handouts` 都是空的）。

## 2. 根本原因

course_parser._find_candidate_pdfs 只在 02 Handouts 沒有 PDF 時才用課本章節（SPEC-018 的規則只看檔案，不看課程原本用哪種講次）；repository._update_lectures 會整批取代講次；cli._on_pdf_detected 掃描後直接 save_course 並排程。

## 3. 修正或規避方式

新增 uses_textbook_lectures／keep_lecture_source／ignored_handouts（course_parser）：課程原本用課本章節時，重新掃描仍只取課本章節。watch 對這種課直接略過、不排程；add_course_folders、register_course_folder、切割後同步講次都套用同一規則。批次排程頁新增提示卡「偵測到講義，但本課以課本章節為講次」，HTTP／MCP 的 list_pending_textbooks 回傳 ignored_handouts。完整的「講義＋課本並用」留在 SPEC-025 R4。（相關程式碼註解加 `Refs: ISSUE-073`）

## 4. 防回歸

tests/test_lecture_source_guard.py（9 項）

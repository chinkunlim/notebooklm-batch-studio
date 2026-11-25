# SPEC-018：課本切割與講次來源

- **狀態**：Implemented <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-25
- **相關任務 / ADR**：TASK-037、SPEC-014（分類與角色）、literature-parser `services/core/analyzer.py` 與 `splitter.py`

## 1. 目標

使用者定案：`02 Handouts` 只放老師講義；完整課本 PDF 放 `01 Materials/`，切割後放在 `01 Materials/<課本名>/`。目前兩門課（115-1_CP31000 10 章、115-1_CP30210 6 章）的課本章節誤放在 `02 Handouts`，而且程式只從 `02 Handouts` 抓講次、沒有切割功能。本規格提供：

1. 依 PDF 書籤把整本課本切成各章 PDF（移植 literature-parser 的章節偵測與切割邏輯，改用本專案已有的 pypdf，不引入 AGPL 的 PyMuPDF）。
2. 講次來源規則：講次先從 `02 Handouts` 抓；**`02 Handouts` 沒有 PDF 時**，改從 `01 Materials` 內有 `.textbook.json` 標記的課本章節資料夾抓。
3. 把既有誤放在 `02 Handouts` 的章節 PDF 搬到 `01 Materials/<課本名>/`，講次編號與 Gemini Notebook 來源不變。

## 2. 使用情境

- **情境 A**：把《Research Methods…》整本 PDF 放進 `01 Materials/`，在課程「進階工具 → 課本切割…」選它，先看到預覽（17 章、各章頁碼、檔名），確認後產生 `01 Materials/Research Methods…/Ch01-Introduction-to-Scientific-Research.pdf` 等檔案，原本整本 PDF 不動。
- **情境 B**：`02 Handouts` 沒有任何講義時，切好的章節自動成為講次；已存在的章節檔不覆寫。
- **情境 C**：既有課程在「進階工具 → 把講義資料夾的課本章節移到 01 Materials…」輸入課本名，預覽要搬的檔案，確認後搬移；講次編號、已上傳的來源與 142 筆既有產出都不受影響。

## 3. 需求

- **必須 (Must)**：
  1. **章節偵測（domain，純計算）**：`find_chapter_sections(entries, total_pages)`。書籤標題符合「`Chapter N …`」或「`N …`」（排除 `1.1` 這類小節編號）的項目視為章節；有多層大綱（例如 Part → Chapter）時，選符合數量最多的那一層；每章結束頁 = 下一個同層或更上層書籤的前一頁，最後一章到全書最後一頁。找不到章節時回傳空清單。
  2. **檔名**：`ChNN-標題.pdf`，標題空白換成 `-`，移除 `/ \ : * ? " < > |`，連續 `-` 合併（與現有 `Ch01-Introduction-to-Scientific-Research.pdf` 一致）。
  3. **切割（adapter：pypdf）**：讀書籤與頁數；把頁碼範圍寫成新 PDF，並保留該章範圍內的子書籤（頁碼改為章內頁碼）。
  4. **切割服務**：`list_textbooks(code)` 列出 `01 Materials`（含別名 `01 Material`）頂層的 PDF；`split_textbook(code, relative_path, dry_run=True)` 預覽或寫出到 `01 Materials/<PDF 檔名主體>/`；該資料夾不存在而課程只有一個已標記的章節資料夾時，改寫到那個資料夾（2026-11-25 補，ISSUE-072：搬移過的章節用課本書名當資料夾，和整本 PDF 檔名通常不同）。同一資料夾已有 `ChNN-` 開頭的檔案就跳過該章，不覆寫；寫入 `.textbook.json`（來源檔名與章節清單）；原始整本 PDF 不動；沒有章節書籤時回錯誤「找不到章節書籤」。套用後同步課程講次。
  5. **講次來源規則**：`course_parser` 先掃 `02 Handouts`；沒有 PDF 時，改掃 `01 Materials` 中有 `.textbook.json` 的子資料夾。`Literature_Review/` 等沒有標記的資料夾永遠不當講次。
  6. **課本當整門課來源（`materials_as_source`）**：上傳 `01 Materials` 時排除有 `.textbook.json` 的章節資料夾，避免整本與各章重複上傳。
  7. **搬移既有章節**：`relocate_handouts(code, book_folder, dry_run=True)` 把該課程 `02 Handouts` 中屬於講次的 PDF 搬到 `01 Materials/<book_folder>/`，寫 `.textbook.json`；講次只更新 `category` 與 `relative_path`，`no`、`sha256`、`source_id`、`upload_status` 不變；目的地已有同名檔時停止並回錯誤，不覆寫。
  8. **三入口**：HTTP `GET /api/courses/{code}/textbooks`、`POST /api/courses/{code}/textbooks/split {relative_path, dry_run}`、`POST /api/courses/{code}/textbooks/relocate-handouts {book_folder, dry_run}`；MCP `list_textbooks`、`split_textbook(…, dry_run=True, confirm=False)`、`relocate_handouts_to_textbook(…, dry_run=True, confirm=False)`；網頁課程「進階工具」兩個選項，先預覽再確認。
- **可選 (Nice to have)**：無書籤 PDF 的掃頁首文字偵測（literature-parser `get_sections_from_text`）。
- **不做 (Out of scope)**：同一門課同時用講義與課本章節當講次（「both」）；自動監看 `01 Materials` 新放入的整本課本。

## 4. 介面 / API

- 預覽回傳：`{"dry_run": true, "source": "01 Materials/Book.pdf", "output_dir": "01 Materials/Book", "chapters": [{"number": 1, "title": "...", "start": 16, "end": 32, "pages": 17, "filename": "Ch01-....pdf", "status": "create|exists"}]}`。
- 錯誤：未知課程 404；路徑不在課程 `01 Materials` 頂層、沒有章節書籤、目的地衝突 → 422。

## 5. 驗收標準

- [x] **場景 18a**：Part→Chapter 大綱、`1.1` 小節、無章節大綱的偵測結果與檔名。（`tests/test_textbook_split.py::test_find_chapter_sections_handles_parts_subsections_and_filenames`）
- [x] **場景 18b**：pypdf 讀書籤、切出正確頁數並保留子書籤。（`test_pypdf_tools_read_outline_and_write_chapter`）
- [x] **場景 18c**：切割預覽不寫檔；套用寫出章節與標記、原檔不動、`02 Handouts` 為空時章節成為講次、`Literature_Review` 不算講次；重跑全部跳過；無書籤 PDF 回錯誤。（`test_split_textbook_preview_apply_rerun_and_lectures`）
- [x] **場景 18d**：搬移既有章節保留講次編號與來源、更新路徑、目的地衝突時停止。（`test_relocate_handouts_keeps_lecture_numbers_and_sources`）
- [x] **場景 18e**：`materials_as_source` 排除章節資料夾。（`test_material_sources_exclude_marked_chapter_folders`）
- [x] **場景 18f**：HTTP、MCP（confirm）、網頁入口。（`test_textbook_entrypoints_http_mcp_and_web`）
- [x] **真實資料**：2026-11-25 使用者同意後套用（備份 `backups/db-20261125-132103`）：生涯諮商與實務 10 個、心理學研究法 6 個章節 PDF 搬到 `01 Materials/<課本>/`，講次編號、來源與 142 筆產出不變，重新掃描與資料庫一致。整本課本切割尚未在真實資料執行（使用者需先放入整本 PDF）。

## 6. 未決問題

- 同一門課若同時有老師講義與課本章節，目前只用講義當講次；若之後需要兩者都產生內容，再加每門課的「講次來源」設定。

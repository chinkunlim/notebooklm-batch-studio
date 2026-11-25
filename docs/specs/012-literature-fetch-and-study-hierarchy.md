# SPEC-012: 整合 literature-fetch 與統一學習目錄結構

- **狀態**：Implemented
- **任務卡**：TASK-025
- **架構決策**：[ADR-011](../adr/011-unified-study-hierarchy-and-literature-fetch.md)

## 1. 背景與目標

將 `literature-fetch` 的學術文獻搜尋、DOI 核對、OpenAthens/EBSCO/華藝/OA PDF 下載與 APA 7 參考文獻管理功能，完整整合進 `notebooklm-batch-studio`，並將課程輸入/輸出與文獻下載對齊使用者的個人學習資料夾結構：

```text
<STUDY_ROOT_DIR>/
└── <學年>-<學期>/<科目>/
    ├── 01 Material/
    │   └── Literature_Review/   # literature-fetch 下載之論文 PDF 與 report.md（可自訂分類與 subfolder）
    ├── 02 Handout/              # 老師教材（支援任意深度的 subfolder；只讀掃描）
    ├── 03 Notes/
    │   ├── NotebookLM/          # NotebookLM 生成的語音、測驗、心智圖、閃卡、導讀（版本化不覆蓋）
    │   └── QA_Notes/            # SPEC-011 探索提問筆記
    ├── 04 Homework/             # 使用者作業（程式不自動讀寫）
    └── 05 Assignments/          # 期中/期末報告（程式不自動讀寫）
```

## 2. 功能需求

1. **統一學習目錄結構 (`study_hierarchy`)**
   - `AppConfig` 支援 `STUDY_ROOT_DIR`（未設定時預設 `<DATA_DIR>/study`），系統內部資料庫、日誌、登入態與隔離區仍保留在 `DATA_DIR/{db,logs,state,needs_review}`。
   - `CourseRecord` 新增 `term`（學年-學期）、`subject`（科目名稱）與 `study_dir`（課程學習目錄路徑）。
   - `course_parser` 支援遞迴掃描 `01 Material/` 與 `02 Handout/` 下的多層子資料夾 PDF（維持既有 `source_id` 不變）。
   - NotebookLM 生成產出物與 QA 筆記輸出至 `<study_dir>/03 Notes/NotebookLM/<講次>_<主題>/` 與 `<study_dir>/03 Notes/QA_Notes/`。
   - 提供安全冪等的資料遷移服務與 CLI/API/MCP 指令，將既有 `DATA_DIR/input/courses/` 與 `DATA_DIR/output/courses/` 平滑遷移至新結構。

2. **文獻收集與管理 (`literature-fetch` 整合)**
   - 支援貼上 APA、作者＋標題、標題或 DOI 清單（中英文皆可），透過 Crossref / OpenAlex / OpenLibrary 補齊中繼資料與 DOI，並產生 APA 7 格式字串（含斜體渲染）。
   - 下載管道依序嘗試：開放取用正式版 → 華藝 Airiti → EBSCO → OpenAthens 授權 Chrome 下載 → 作者稿/預印本，並以 `pypdf` 核對 PDF 標題。
   - 保留**人工處理模式**：遇到機器人驗證或校外登入時，啟動可視 Chrome 等待使用者完成操作後繼續。
   - 資料庫 `literature_items` 表透過 `course_code` 外鍵關聯課程，記錄目標分類（預設 `01 Material`）、目標子資料夾（預設 `Literature_Review`）、匯入狀態與 `source_id`。
   - 支援一鍵將已下載 PDF 匯入關聯課程的 Gemini Notebook 來源。

3. **三入口一致（Web UI + HTTP API + MCP）**
   - Web UI 左側 Sidebar 新增「文獻收集」圖示與專屬頁面（貼上文獻、選擇科目/分類/子資料夾、人工處理模式開關、進度追蹤、重試/重新辨識/試抓正式版/刪除、PDF.js 內嵌預覽含縮放、歸檔至課程、生成／複製已勾選 APA 7 斜體清單、下載 `report.md`）。
   - HTTP API `/api/literature/*` 與 MCP 工具 `list_literature`、`export_literature_apa`、`add_literature`、`process_literature`、`refresh_literature`、`import_literature_to_course`、`unarchive_literature`、`delete_literature`、`sync_literature_notebook`、`query_literature_notebook`、`generate_literature_review`（會改資料者含 `confirm` 保護）同步提供。舊的 `migrate_study_layout` 已由 SPEC-023 停用（ADR-018），改用 `consolidate`。

## 3. 繼承自 `literature-fetch` 的核心設計原則（原 ADR-001 ~ 007）

1. **開放取用優先，Chrome 走機構授權、不繞過驗證**：純 HTTP 優先抓取開放取用 PDF；遇出版社防護或校外登入時，改用 Playwright Chrome（搭配 OpenAthens redirector），絕不自動破解 CAPTCHA / Cloudflare Turnstile，無人值守模式下標記 `needs_review` 並記錄網域。
2. **正式版優先（Version of Record First）**：下載順序嚴格為「開放取用正式版 → 華藝（Airiti）→ EBSCO → 出版社授權頁 → 作者稿 / 預印本（arXiv / OSF）」。僅拿到作者稿時標註 `downloaded_copy` 並提示頁碼以正式版為準；執行「試抓正式版（refresh）」時僅接受正式版，找不到時保留原檔不覆蓋。
3. **本地 APA 解析 + Crossref / OpenAlex 核對**：優先用 DOI 查詢 Crossref / OpenAlex；無 DOI 時以標題與第一作者＋年份比對搜尋結果，拒絕非出版物（dataset / peer-review）與他篇論文誤配。
4. **書籍與中文文獻專屬管線**：書籍透過 OpenLibrary 補齊最新版本與 ISBN，標註 `borrow`（請向圖書館借閱）而不盲目抓論文 API；中文文獻透過華藝（Airiti）辨識並輸出中文 APA 7 格式。
5. **PDF 標題驗證**：所有下載回來的 PDF 皆透過 `pypdf` 讀取前幾頁文字並比對目標標題，避免網站回傳錯誤論文或空白驗證頁（無法解析文字層的掃描檔才放行）。

## 4. 整合後新增進階能力

- **PDF.js 內嵌預覽**：於列表列下方展開摺疊預覽，支援放大／縮小／三段預設倍率與 `✕` 關閉，避免瀏覽器直接觸發下載。
- **Excel 式表頭多條件排序與篩選**：`序`、`狀態`、`APA 7th`、`歸檔位置` 皆提供整合式表頭選單，支援多欄位疊加排序（`1↑`、`2↓`）、逐項勾選篩選，以及 `APA 7th` 即時關鍵字搜尋。
- **Gemini 文獻總庫與 Literature Review**：自動建立並維護跨課程的 `Literature Library (文獻總庫)` Gemini Notebook，支援將已下載 PDF 同步至總庫進行跨文獻問答查詢，以及依西方重點大學格式生成 7 段式 Literature Review（遇配額限制時自動等待恢復並續傳）。

## 5. 測試與驗證

- **單元測試**（`tests/literature/`，108 項）：`test_apa.py`、`test_apa_format.py`、`test_free_text.py`、`test_chinese.py`、`test_airiti.py`、`test_books.py`、`test_literature.py`、`test_tracker.py` 及離線 fixtures（`tests/fixtures/{apa_list.md,openalex_work.json,crossref_search.json}`）。
- **整合測試**（`tests/test_literature_and_hierarchy.py`，5 項）：HTTP/MCP 端點、課程歸檔與 `scratch/literature` 掃描、舊資料夾結構遷移與遞迴教材掃描。

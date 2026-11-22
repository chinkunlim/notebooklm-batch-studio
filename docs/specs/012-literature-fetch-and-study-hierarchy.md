# SPEC-012: 整合 literature-fetch 與統一學習目錄結構

- **狀態**：Approved
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
   - Web UI 左側 Sidebar 新增「文獻收集」圖示與專屬頁面（貼上文獻、選擇科目/分類/子資料夾、人工處理模式開關、進度追蹤、重試/重新辨識/重新整理/刪除、開啟 PDF、匯入課程、複製 APA 7 斜體清單、下載 `report.md`）。
   - HTTP API `/api/literature/*` 與 MCP 工具 `list_literature`、`add_literature`、`process_literature`、`import_literature_to_course`、`delete_literature`（含 `confirm` 保護）同步提供。

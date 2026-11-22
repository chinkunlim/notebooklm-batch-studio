# ADR-011：整合 literature-fetch 與統一學習目錄結構 (<學年>-<學期>/<科目>/<分類>)

- **狀態**：Accepted
- **日期**：2026-11-22
- **Agent**：`antigravity`
- **任務**：`TASK-025`

## 1. 背景與問題

使用者同時維護 `notebooklm-batch-studio`（課程 PDF 轉筆記、測驗、語音）與 `literature-fetch`（APA 文獻搜尋、DOI 核對與論文 PDF 下載），且個人學習資料夾採用固定階層：
`<學年>-<學期>/<科目>/<分類>[/<subfolder>]`（分類含 `01 Material`、`02 Handout`、`03 Notes`、`04 Homework`、`05 Assignments`）。
原本 `notebooklm-batch-studio` 採用扁平的 `DATA_DIR/input/courses/` 與 `DATA_DIR/output/courses/`，與使用者的個人學習目錄及文獻管理流程脫節。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. 維持兩套獨立系統與扁平資料夾 | 不需修改既有課程掃描邏輯 | 需手動搬運下載的論文 PDF，且目錄與使用者習慣不符 |
| B. 將 literature-fetch 併入本專案，並對齊 `<學年>-<學期>/<科目>/<分類>` 統一目錄（系統 `db/logs/state/needs_review` 仍隔離於 `DATA_DIR`） | 下載論文直接歸檔 `01 Material/Literature_Review/`、AI 筆記集中於 `03 Notes/NotebookLM/`，資料庫外鍵完整關聯課程 | 需升級課程掃描支援多層子資料夾，並遷移既有 `DATA_DIR` 課程資料夾 |

## 3. 決策與理由

採用 **方案 B**。兩個專案使用相同的分層架構與依賴（FastAPI、SQLAlchemy、Alembic、Playwright、pypdf），僅需補充 `httpx`。將文獻下載集中於 `01 Material/Literature_Review/`、AI 產出集中於 `03 Notes/NotebookLM/`，既可保持使用者原始教材唯讀不混亂，又能讓文獻下載與課程 NotebookLM 來源形成單一閉環。

## 4. 影響與代價

- 新增 `STUDY_ROOT_DIR`（預設 `<DATA_DIR>/study`）與課程欄位 `term`、`subject`、`study_dir`。
- 新增 `literature_items` 資料表與 `CourseRecord` 的 `course_code` 外鍵關聯。
- 既有 `DATA_DIR/input/courses/` 與 `DATA_DIR/output/courses/` 透過冪等遷移函式整理至新結構。
- Web UI Sidebar 新增「文獻收集」圖示與專屬頁面，同步提供 HTTP API 與 MCP 工具。

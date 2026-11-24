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

## 5. 繼承自 `literature-fetch` 之架構決策對照（ADR-001 ~ ADR-008）

> `TASK-025` 併入原獨立專案 `/Users/limchinkun/Desktop/projects/literature-fetch`；下表逐條對照原 `ADR-001 ~ ADR-008` 於本專案 `ADR-011` 及後續紀錄中之承接狀況：

| 原 `literature-fetch` ADR | 來源檔案 (`/Users/limchinkun/Desktop/projects/literature-fetch/docs/adr/...`) | `ADR-011` 涵蓋狀況與核心摘要 |
|---|---|---|
| **ADR-001** 文獻下載策略：開放取用優先、Chrome 走機構授權、不繞過驗證 | `001-literature-download-strategy.md` | 原 §1–3 未展開細節，**補摘要**：開放取用（arXiv/明列網址/OpenAlex）優先；需機構授權時以有頭 Chrome 走 OpenAthens（僅於 `*.openathens.net` 填寫 `.env` 之 `LIBRARY_EMAIL`/`LIBRARY_PASSWORD`，詳本專案 `ADR-013`），絕不繞過 Cloudflare/CAPTCHA；頁面內 `fetch()` 下載並以 `pypdf` 比對前幾頁標題（`adapters/literature/browser.py`、`services/literature/literature.py`）。 |
| **ADR-002** APA 清單轉換：本地解析 + Crossref 核對 | `002-apa-list-conversion.md` | 原 §1–3 未展開細節，**補摘要**：由 `domain/literature/apa.py` 解析作者/年份/標題/DOI/arXiv，經 `services/literature/reference_builder.py` 與 `crossref.py` / `openalex.py` 核對（標題雙向吻合或主標題>=3關鍵字+同第一作者、年份差<=1、排除 dataset/peer-review）。 |
| **ADR-003** 下載順序：正式版優先 | `003-version-of-record-first.md` | 原 §1–3 未展開細節，**補摘要**：優先順序為 OpenAlex OA `publishedVersion` → EBSCO → 出版社 → 預印本/作者稿；`refresh` 嘗試升級為正式版並將舊檔移至 `superseded/`（`adapters/literature/{ebsco,openalex}.py`、`services/literature/literature.py`）。 |
| **ADR-004** 無人值守模式與書籍處理 | `004-unattended-mode-and-books.md` | 原 §1–3 未展開細節，**補摘要**：預設 `wait_seconds=0` 不卡整批，遇驗證記 `NeedsUserError` 改標 `needs_review`，`--interactive` / 互動模式才等候；書籍經 `openlibrary.py` 查詢最新版本，僅 `public` 無限制掃描檔自動下載，其餘標需借閱。 |
| **ADR-005** Markdown 清單輸入與 APA 7 格式 | `005-markdown-reference-list.md` | 原 §3 簡述表單整合，**補摘要**：保留完整 APA 7th 生成規則（作者最多 20 位、句首大寫、期刊與卷斜體、`--` en dash、DOI 網址），整合後輸入與結果改由 SQLite + Web UI／`output/literature/report.md` 驅動（`SPEC-012`）。 |
| **ADR-006** SQLite 資料庫 + 共用 Runner | `006-sqlite-store-and-runner.md` | 原 §4 已提及 `literature_items` 與 `CourseRecord` 外鍵，**補摘要**：合併至統一 `DATA_DIR/db/app.db`（`literature_items` + `literature_jobs`，Alembic 遷移），由 `services/literature/jobs.py` 單一背景工作執行期（`LiteratureJobRunner`）共用，並於 `TASK-032`（`ISSUE-054`）補齊啟動關閉殘留 `running` 工作。 |
| **ADR-007** 中文文獻：華藝（Airiti）辨識與下載、中文 APA 格式 | `007-chinese-references-airiti.md` | 原 §1–3 未展開細節，**補摘要**：含中文字目啟動 Chrome 經 `adapters/literature/airiti.py` 搜尋與擷取 `citation_*`，下載順位「華藝 → EBSCO → 出版社」；採用全形標點映射、bigram 中文標題比對與亂碼 PDF 容錯（`ISSUE-042`），並依台灣慣例輸出中文 APA 7（`domain/literature/apa_format.py`）。 |
| **ADR-008** 本機網頁 + JSON API（127.0.0.1） | `008-local-web-app-and-api.md` | **原 §3–4 已涵蓋**：由單獨 FastAPI 進程整併為本專案統一 `127.0.0.1:8768` FastAPI 服務，具備 `HostValidationMiddleware` / CORS CSRF 防護，並依本專案規則 13 對齊 HTTP、MCP（`mcp_literature.py`）與 Web UI 側欄三端入口。 |

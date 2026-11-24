# 學習資料庫統一與完整學習紀錄 Implementation Plan

> **執行者須知（Antigravity 或任何 Agent）：** 依任務編號逐一執行，每完成一個 Step 就把 `- [ ]` 改成 `- [x]`。每個任務：先建或接手任務卡 → 依核心規則 16 先寫失敗測試並貼出紅燈輸出 → 實作 → 貼出綠燈輸出 → `agentctl check` 零警告 → `agentctl commit`。Phase 之間停下來回報，經使用者同意再進下一個 Phase。**不要 push。**

**Goal:** 讓 `DATA_DIR/study/<學期>/<課程>/<分類>` 成為唯一的課程資料結構、`DATA_DIR/scratch/<種類>/` 成為唯一的未歸檔區，課程以「學期＋課號」識別，可一次登錄過去學期（113-1 起）的課程而不消耗額度，並提供跨學期、可匯出 Markdown／PDF 的完整學習紀錄；同時清掉這次盤點找到的所有路徑、身分與紀錄缺口。

**Architecture:** 新增 `domain/course_identity.py`（課號解析、代碼組合）、`domain/study_layout.py`（分類名稱、別名、角色）；`AppConfig` 提供全部 DATA_DIR 子路徑。新服務 `study_library`（掃描學期樹、只登錄不生成）、`filing`（歸檔／撤銷歸檔）、`course_lifecycle`（封存、改代碼）、`learning_record`（彙整與匯出）、`legacy_consolidation`（一次性整併），每個都接 HTTP、MCP、網頁三入口（核心規則 13）。資料庫加 `courses.status`、`courses.course_no`。

**Tech Stack:** Python 3.11（uv）、FastAPI、SQLAlchemy 2 + Alembic（SQLite）、MCP（`mcp.server.mcpserver`）、原生 JS、unittest；PDF 匯出沿用 `services/converters/note_pdf_renderer.render_markdown_to_pdf`。

**Spec:** `docs/specs/014-study-library-and-learning-record.md`（Task 1 依下方「需求」寫成）；決策 `docs/adr/014-course-identity-and-study-layout.md`。

## 交接說明（2026-11-24，Claude Code → Antigravity）

- **計畫狀態：** Claude Code 撰寫，已對照兩次審查與你的 6 筆 commit（`3976c94`…`3e2536d`）更新；下方「盤點項目對照表」中標 ✅ 的不需再做。
- **開工前的現況（2026-11-24 實測）：**
  - 課程資料夾解析是錯的：`services/course_parser.py::parse_course_folder_name("CP__30000-團體諮商")` 回傳 `('CP', '30000-團體諮商')`，所有 `CP__` 課程都會拿到代碼 `CP` 而互相覆蓋。**Task 2 完成前，不要用真實的 `study/115-1/CP__…` 資料夾登錄課程**。舊函式的呼叫端：`course_parser.py:182`、`services/__init__.py:7,19`、`tests/test_course_parser.py:11-40`（Task 7 改用 `domain/course_identity.parse_course_folder`；舊函式留給 `BIO101 普通生物學`、`115-1 心理學研究法` 這類舊命名，測試要同時涵蓋兩種）。
  - 閃卡跨課程讀取仍在 `services/study_service.py:213`（Task 6）。
  - 仍存在的數量（含註解，僅供對照）：舊佈局 `courses_input_dir`／`courses_output_dir` 31 處、單數分類字面 32 處、`config` 外寫死 DATA_DIR 子路徑 22 處、`entrypoints`／`config` 外 `load_config()` 12 個檔案。
- **超出本計畫範圍（不要順手做）：** SPEC-001 的「完成時 macOS 通知」尚未實作，另開任務；11 條「待實機」驗收由使用者處理。
- **需要使用者的地方：** Q1–Q5（下方）在 Task 16 前逐項確認；`.env` 的任何修改先徵得同意。

## 需求（使用者已確認，2026-11-24）

1. 學習資料只放在 `DATA_DIR/study/`（`projects-data/notebooklm-batch-studio/study/`）；iCloud 等雲端只做備份，程式不讀寫雲端資料夾。
2. 結構 `study/<學期>/<課程資料夾>/<分類>/[子資料夾…]`，學期如 `113-1`…`115-1`。
3. 課程資料夾命名 `CP__30000-團體諮商`、`GC__68210-和 AI 一起寫程式`、`YY__5061AA-體育 (三)_超慢跑 AA`。
4. 學期資料夾也有非課程資料夾（`Course Outline`、`專題`）與散檔（`.epub`、`.md`、`.docx`）。
5. 分類：`01 Materials`＝課本、`02 Handouts`＝老師給的 PDF／PPT、`03 Notes`＝專案生成的筆記與個人隨筆、`04 Homework`＝作業、`05 Assignments`＝期中期末報告；分類內可有子資料夾。
6. `scratch/` 與 `study/` 同層：存放尚未歸檔的結果與撤銷歸檔退回的檔案。
7. 要能開啟舊學期課程，打造完整學習紀錄（教材、NotebookLM 產出、NoteStudio 筆記、問答筆記、測驗與錯題、文獻、作業報告、讀書時間、記憶強度），可匯出 Markdown 與 PDF。

## 待使用者決定（計畫先用預設值，Task 1 寫進 SPEC-014「未決問題」）

| # | 問題 | 預設 |
|---|---|---|
| Q1 | `deleted/`（344 MB）保留政策 | 永久保留；只提供列出與「使用者 `confirm=True` 才刪除」的手動清理，不自動刪 |
| Q2 | `02 Handouts` 的 `.pptx`／`.docx` | 只列入學習紀錄，不轉檔、不上傳 |
| Q3 | 文獻 PDF 預設歸檔位置 | `01 Materials/Literature_Review`（以 MATERIALS 角色解析，不寫死名稱） |
| Q4 | `01 Materials`（課本）是否上傳為 NotebookLM 來源 | 預設不上傳；課程設定可勾選「課本作為整門課來源」 |
| Q5 | 現有課程對照 | `115-1`（生涯諮商）→ `115-1_CP31000`（`CP__31000-生涯諮商與實務`）；`心理學研究法` → `CP__30210`；`midterm-submission/` 屬於哪門課 — Task 16 執行前逐項請使用者確認 |

## Global Constraints

- 依 `AGENTS.md`：完整 docstring、模組 logger、單向分層 `entrypoints → adapters → services → domain → config`、函式 ≤ 40 行、參數 ≤ 4、巢狀 ≤ 3、檔案 ≤ 500 行；`agentctl check` 零警告（核心規則 15）。
- 只用 `uv run …`。
- 課程代碼 `<學期>_<課號>`（例 `115-1_CP30000`）；課號＝資料夾 `__` 兩側英數字相接轉大寫（`CP__30000`→`CP30000`、`YY__5061AA`→`YY5061AA`）；代碼必須通過 `domain/path_safety.validate_path_segment`。
- 分類預設 `01 Materials`、`02 Handouts`、`03 Notes`、`04 Homework`、`05 Assignments`；`01 Material`、`02 Handout` 為別名（讀取合併、建立不重複）；名稱可用 `.env` 的 `STUDY_CATEGORIES`（5 個，逗號分隔）覆寫。
- 講次只取自 `02 Handouts`（含子資料夾）的 PDF；`01 Materials` 的 PDF 是課程教材，不成為講次。
- 產出寫在 `03 Notes/NotebookLM`、`03 Notes/NoteStudio`、`03 Notes/QA_Notes`；`03 Notes` 中其他檔案（使用者隨筆）不得移動或覆寫。
- 上傳的自訂來源存 `02 Handouts/_uploaded/`；任何新寫入都不得落在 `input/courses` 或 `output/courses`。
- 未歸檔一律 `scratch/<種類>/`，種類固定：`literature`、`notes`、`outputs`、`uploads`、`unarchived`。
- 舊學期課程以 `record-only` 登錄（不排生成、不讀額度），預設 `status=archived`；封存課程不進佇列、Today、到期複習、課程選單預設清單。
- 會修改資料的 MCP 工具一律 `confirm: bool = False`，未確認回 `{"confirmed": false, "warning": "..."}`。
- 不刪除使用者在 `study/` 的任何檔案；刪除課程只移除資料庫並提示改用「封存」；不自動刪除本機或遠端資料。
- 程式不讀寫 iCloud 路徑；舊學期資料由使用者自行複製到 `DATA_DIR/study/`。
- Commit：`python3 scripts/agentctl.py commit --agent <名字> --model <模型> -m "<English>"`；找到錯誤根因立刻用 `adr-issue-tracker` 寫 known-issue（核心規則 4）；未經同意不 push。

## Review Focus

1. 課程資料夾含空白、括號、全形字（`YY__5061AA-體育 (三)_超慢跑 AA`）→ 課號 `YY5061AA`、課名完整保留。（Task 2）
2. 同一課號兩個學期都修（重修）→ `114-1_CP30000`、`115-1_CP30000` 兩門課資料不混，閃卡、測驗、筆記各自讀自己的資料夾。（Task 2、Task 6、Task 7）
3. 同時有 `02 Handout` 與 `02 Handouts` → 講次合併不重複，不多建資料夾。（Task 3）
4. `02 Handouts` 裡的 `.pptx`／`.docx` → 不是講次、不上傳，但出現在學習紀錄。（Task 3、Task 12）
5. 改代碼時有 `running` 工作、或新代碼已存在 → 拒絕，資料庫與檔案不變。（Task 11）

---

## 盤點項目對照表（每項都必須有對應任務）

| 來源 | 項目 | 任務 |
|---|---|---|
| Antigravity 審查後 | `LEGACY_NOTE_STUDIO_DIR` 未設定，舊筆記無法匯入 | 16 |
| 同上 | 以 `file_path` 上傳限制在課程資料夾；上傳檔仍寫進 `input/courses/<code>/_uploaded_sources` | 6 |
| 同上 | MCP confirm 回應格式只統一 4 個檔案 | ✅ 已由 Antigravity `9d6ef12` 完成（57 支工具，2026-11-24 實測 54 支回 `confirmed:false`，其餘 3 支為測試輸入或 dry-run 預設）；Task 13 只保留回歸測試 |
| 同上 | `tests/gemini/test_quota_resume_parser.py` 的 `ISSUE-065` 前綴 | ✅ `9d6ef12` 已修 |
| 同上 | 今天的對話紀錄尚未建立 | 17 |
| 交給 Antigravity 的 A–F | 規格驗收勾選、任務溯源、note-studio 紀錄與被刪規則、literature ADR 對照、ISSUE-053／054 | ✅ `3976c94`、`13dff45`、`9d6ef12`、`8ab99cb`（2026-11-24 查收：438 測試通過、check 0 警告）；餘：11 條「待實機」驗收、CHANGELOG 缺 TASK-033 與 ISSUE-042..044 → 17 |
| 查收時新發現 | ISSUE-054 的修法會在**另一個程序**（MCP stdio）啟動時把仍在執行的文獻工作標成 failed（已重現） | ✅ Antigravity `d3f428e`（ISSUE-057、TASK-034）；2026-11-24 以兩個真實程序重現：執行中不被關閉、完成為 done、程序崩潰後由下一程序關閉為 failed |
| 查收時新發現 | 框架更新做到一半：7 個檔案未提交，`agentctl scan` 警告 AGENTS.md 缺核心規則 16 | ✅ Antigravity `3e2536d`（v3.6.0／template `8c52c90`，規則 16 與母版一致，scan 100/100） |
| 核心規則 16（新） | 新功能須走 SDD → BDD → TDD：規格以 `Given / When / Then` 列驗收場景 | 1（SPEC-014 §5 改寫為情境）、每個功能任務的 Step 1 測試名稱對應情境 |
| 查收時新發現 | Gemini 登入新增 `state/gemini_profile` 寫死 3 處、`gemini_auth_service.py:75` 新增 `load_config()` 後備 | 4 |
| 盤點 Part 1-1 | 課程代碼三種規則不一致 | 2、11、16 |
| Part 1-2 | 三種資料夾佈局並存；監看器只看 `input/courses`；資料夾挑選捷徑只指向 `input/courses`；文件仍寫舊佈局 | 1、6、9、17 |
| Part 1-2 補 | `output/courses`／`input/courses` 仍被 14 處程式寫入或讀取（上傳、問答筆記後備、閃卡、摘要報告、刪除課程、遷移） | 6 |
| Part 1-3 | 7 處寫死 DATA_DIR 子路徑、7 處 `load_config()` 後備 | 4 |
| Part 1-4 | 109 份 note-studio 筆記、`心理學研究法` 未登錄、`midterm-submission/` 散置、`deleted/` 344 MB、`deleted/115-1-20261112-182701` 內容待查 | 15、16 |
| Part 1-5 | 三組 Google／瀏覽器登入沒有統一說明與狀態（Gemini 已有 `/api/notes/gemini/auth-status`） | 14 |
| Part 1-6 | 筆記不在資料庫，學習紀錄需讀檔 | 12 |
| Part 2 | 只登錄不生成、封存、選單依學期分組、跨課程學習紀錄、匯入筆記本要有學期 | 5、7、9、11、12、13 |
| 決策 4 | 學習紀錄含讀書時間、記憶強度；匯出 Markdown＋PDF | 12 |
| 使用者建檔習慣 | 分類複數名、子資料夾、課本不是講次、PPT、`03 Notes` 個人隨筆不可動 | 3、6、12 |
| 同上 | 文獻預設分類寫死 `01 Material`（DB 預設、tracker、HTTP、MCP、index.html、3 支 JS） | 3、5 |
| 同上 | `scratch/` 統一未歸檔、撤銷歸檔通用化（不只文獻） | 4、10 |
| 同上 | 現有 `study/115-1/生涯諮商` 改名為校方命名、單數分類併入複數、DB 路徑跟著更新 | 15、16 |
| 同上 | `專題` 等非標準資料夾可手動登錄為課程 | 7 |
| 同上 | 新增本學期課程時要落在 study 樹（資料夾挑選、外部資料夾複製進來） | 8 |
| iCloud 只是備份 | 程式不碰雲端；安裝／更新要建立 `study/`、`scratch/` 並套用 migration（核心規則 14） | 4、17 |
| 這次新發現 | 閃卡後備搜尋跨課程（`study_service.py:210-213`）會讀到別門課 | 6 |
| 2026-11-24 實測 | `parse_course_folder_name("CP__30000-團體諮商")` → `('CP', '30000-團體諮商')`，同系所課程代碼全部撞成 `CP` | 2、7 |
| 這次新發現 | 刪除課程會連帶刪掉資料庫中的學習紀錄，學習紀錄會缺 | 11 |
| 這次新發現 | 改代碼需同步 `course.toml`、網頁偏好的課程、筆記狀態 JSON、`scratch/notes/<code>`、問答筆記 frontmatter、Notebook 標題規則 | 11 |
| 這次新發現 | `study_migration.py`、`study_migration_repo.py` 寫死 `02 Handout` | 3 |
| 這次新發現 | ADR-011 需標註被 ADR-014 修訂；展示頁假資料需支援學期分組 | 1、17 |

---

## 檔案結構

| 檔案 | 動作 | 責任 |
|---|---|---|
| `docs/specs/014-study-library-and-learning-record.md`、`docs/adr/014-course-identity-and-study-layout.md`、`docs/known-issues/057..` | 新增 | 規格、決策、這次盤點的已知問題 |
| `domain/course_identity.py` | 新增 | 課程資料夾解析、代碼組合／拆解 |
| `domain/study_layout.py` | 新增 | 分類名稱、別名、角色 |
| `domain/study_hierarchy.py`、`services/course_parser.py`、`services/study_migration.py`、`adapters/db/study_migration_repo.py` | 修改 | 改用 `study_layout` |
| `config/settings.py` | 修改 | 全部 DATA_DIR 子路徑、`STUDY_CATEGORIES` |
| `services/study_library.py` | 新增 | 掃描學期樹、只登錄不生成、手動登錄 |
| `services/filing.py` | 新增 | 歸檔／撤銷歸檔（scratch ↔ 課程分類） |
| `services/course_lifecycle.py`、`adapters/db/course_identity_repo.py` | 新增 | 封存／恢復、改代碼 |
| `services/learning_record.py` | 新增 | 學習紀錄、Markdown／PDF 匯出 |
| `services/legacy_consolidation.py` | 新增 | 一次性整併（dry-run 預設） |
| `services/auth_status.py` | 新增 | 三組登入狀態 |
| `entrypoints/http/study_library.py`、`entrypoints/mcp_study_library.py`、`entrypoints/static/studio-record.js` | 新增 | 三入口 |
| `alembic/versions/20261125_<rev>_course_status_and_course_no.py` | 新增 | `courses.status`、`courses.course_no`、文獻分類預設值 |
| `tests/test_course_identity.py`、`test_study_layout.py`、`test_settings_paths.py`、`test_old_layout_retired.py`、`test_study_library.py`、`test_filing.py`、`test_course_lifecycle.py`、`test_learning_record.py`、`test_study_library_api.py`、`test_auth_status.py`、`test_legacy_consolidation.py` | 新增 | 各任務測試 |

---

## Phase G：開工前閘門

### Task 0: 確認 Antigravity 的工作已提交並驗收證據；記錄盤點問題

**Files:** `docs/known-issues/057-*.md` 起（`tracker_cli.py --add-issue`）

- [x] **Step 1:** 確認 `git status --short` 只剩本計畫檔，且 Antigravity 的 6 筆 commit（`3976c94`…`3e2536d`）經使用者同意已推送（註：依本次執行規則不執行 push，6 筆本機 commit 暫留於 local `main`）；`agentctl scan` 100/100（框架更新已由 `3e2536d` 完成，目前實測 92/100 僅提示遠端模板可更新，其餘全 PASS）。
- [x] **Step 2:** A–F 已於 2026-11-24 查收（見對照表）；本步驟只需在 SPEC-014 §5 引用這四個 commit。
- [x] **Step 3:** 以 `adr-issue-tracker` 為這次盤點登錄 known-issue（狀態 open，修正任務寫在 fix 欄）：課程代碼三規則不一致（→Task 2/11/16）、監看器只看 `input/courses`（→9）、資料夾挑選捷徑（→6）、`output/imported_sources` 佈局（→9）、舊佈局寫入點（→6）、`load_config()` 後備（→4）、閃卡跨課程讀取（→6）、刪除課程遺失學習紀錄（→11）。
- [x] **Step 4:** 建任務卡 `python3 scripts/agentctl.py task create "Study library, course identity and learning record" --agent <名字>`；Commit `-m "docs(issues): record study-layout and course-identity audit findings"`

### Task 0b: ~~跨程序誤殺修正~~ — 已由 Antigravity `d3f428e` 完成（ISSUE-057），本計畫不需再做

## Phase 0：身分、分類、路徑、舊佈局退場

### Task 1: SPEC-014、ADR-014 與規則文件

**Files:** Create `docs/specs/014-study-library-and-learning-record.md`、`docs/adr/014-course-identity-and-study-layout.md`；Modify `docs/specs/SPECS.md`、`docs/adr/011-unified-study-hierarchy-and-literature-fetch.md`（狀態加「部分由 ADR-014 修訂」）、`docs/standards/PROJECT_RULES.md` §1、§2（命名與位置改為 study／scratch）、§3（若有例外寫理由）、`README.md`（快速開始的資料夾說明、監看一節）

- [x] **Step 1:** SPEC-014（依核心規則 16 與 `docs/standards/testing/sdd_bdd_tdd.md`）：§1–§3 寫入「需求」7 條與 Global Constraints；§4 介面表取自 Task 13；§5 以 `Given / When / Then` 寫驗收情境，每個情境標出對應的測試名稱（本計畫各任務 Step 1 的測試）；§6 未決問題放 Q1–Q5。
- [x] **Step 2:** ADR-014：方案 A 學期＋課號（採用）／B 自訂代碼／C UUID；決策含代碼格式、分類預設與別名、講次只取 `02 Handouts`、`record-only`、`scratch/<種類>`、刪除課程改為建議封存。
- [x] **Step 3:** `python3 scripts/agentctl.py check` 結束碼 0；Commit `-m "docs: add SPEC-014 and ADR-014, update project rules for study library"`

### Task 2: 課程身分（domain）

**Files:** Create `domain/course_identity.py`；Test `tests/test_course_identity.py`

**Interfaces — Produces:**
- `@dataclass(frozen=True) class CourseFolderInfo: course_no: str; name: str; is_course: bool`
- `parse_course_folder(folder_name: str) -> CourseFolderInfo`（規則 `^([A-Za-z]{1,6})_{1,2}([0-9A-Za-z]+)-(.+)$`）
- `make_course_code(term: str, course_no: str) -> str`、`split_course_code(code: str) -> tuple[str, str]`
- `TERM_PATTERN = re.compile(r"^\d{2,4}-\d{1,2}$")`
- `notebook_title(course_no: str, name: str, term: str) -> str` → `"[CP30000] 團體諮商 (115-1)"`

- [x] **Step 1: 失敗測試**

```python
def test_parses_school_course_folders(self):
    self.assertEqual(parse_course_folder("CP__30000-團體諮商"), CourseFolderInfo("CP30000", "團體諮商", True))
    self.assertEqual(
        parse_course_folder("YY__5061AA-體育 (三)_超慢跑 AA"),
        CourseFolderInfo("YY5061AA", "體育 (三)_超慢跑 AA", True),
    )


def test_non_course_folders(self):
    for name in ("Course Outline", "專題", "115-1", ".DS_Store", "生涯諮商"):
        self.assertFalse(parse_course_folder(name).is_course, name)


def test_codes(self):
    self.assertEqual(make_course_code("115-1", "CP30000"), "115-1_CP30000")
    self.assertNotEqual(make_course_code("114-1", "CP30000"), make_course_code("115-1", "CP30000"))
    self.assertEqual(split_course_code("115-1_CP30000"), ("115-1", "CP30000"))
    self.assertEqual(split_course_code("BIO101"), ("", "BIO101"))
    self.assertEqual(notebook_title("CP30000", "團體諮商", "115-1"), "[CP30000] 團體諮商 (115-1)")
    with self.assertRaises(PathSafetyError):
        make_course_code("115-1", "CP/30000")
```

- [x] **Step 2:** `uv run python -m unittest tests.test_course_identity -v` → 失敗
- [x] **Step 3:** 實作
- [x] **Step 4:** 同指令 → `OK`
- [x] **Step 5:** Commit `-m "feat(domain): parse school course folders into term-scoped course codes"`

### Task 3: 分類名稱、別名、角色，並替換所有寫死的分類

**Files:**
- Create `domain/study_layout.py`；Test `tests/test_study_layout.py`
- Modify（全部改用 `StudyLayout`／角色，不再寫死字串）：`domain/study_hierarchy.py:3,16-24,90,115`、`services/course_parser.py:99-130`、`services/study_migration.py:67,151,167`、`adapters/db/study_migration_repo.py:87-89`、`adapters/db/literature_repository.py:66`、`domain/literature/tracker.py:38,55`、`services/literature/manager.py:171`、`entrypoints/http/literature.py:37`、`entrypoints/mcp_literature.py:40`、`entrypoints/static/index.html:581-585`、`studio-literature-actions.js:67`、`studio-literature-rows.js:10,37`、`studio-literature.js:183`（前端分類清單改由 `GET /api/study/layout` 取得，見 Task 13）

**Interfaces — Produces:**
- `class CategoryRole(str, Enum)`: `MATERIALS`、`HANDOUTS`、`NOTES`、`HOMEWORK`、`ASSIGNMENTS`
- `@dataclass(frozen=True) class StudyLayout: names: dict[CategoryRole, str]; aliases: dict[CategoryRole, tuple[str, ...]]`
- `DEFAULT_LAYOUT`、`layout_from_names(raw: str) -> StudyLayout`（必須 5 個，否則 `ValueError`）
- `StudyLayout.category_dirs(course_dir: Path, role: CategoryRole) -> list[Path]`、`.primary_dir(course_dir, role) -> Path`、`.ensure_tree(course_dir) -> None`、`.role_of(name: str) -> CategoryRole | None`、`.as_dict() -> dict[str, str]`
- `DEFAULT_LITERATURE_SUBFOLDER = "Literature_Review"` 不變；文獻預設分類＝`layout.names[MATERIALS]`

- [x] **Step 1: 失敗測試**

```python
def test_singular_and_plural_handouts_merged(self):
    # 02 Handout/a.pdf、02 Handouts/sub/b.pdf、02 Handouts/c.pptx
    self.assertEqual(
        {d.name for d in DEFAULT_LAYOUT.category_dirs(course, CategoryRole.HANDOUTS)},
        {"02 Handout", "02 Handouts"},
    )
    lectures = scan_course_directory(course).lectures
    self.assertEqual(sorted(l.filename for l in lectures), ["a.pdf", "b.pdf"])
    self.assertEqual([l.relative_path for l in lectures if l.filename == "b.pdf"], ["02 Handouts/sub/b.pdf"])


def test_materials_are_not_lectures(self):
    self.assertEqual([l.filename for l in scan_course_directory(course_with_textbook).lectures], ["w1.pdf"])


def test_ensure_tree_respects_alias(self):
    (course / "01 Material").mkdir(parents=True)
    DEFAULT_LAYOUT.ensure_tree(course)
    self.assertFalse((course / "01 Materials").exists())
    self.assertTrue((course / "05 Assignments").is_dir())


def test_role_of_and_custom_names(self):
    self.assertEqual(DEFAULT_LAYOUT.role_of("02 Handout"), CategoryRole.HANDOUTS)
    with self.assertRaises(ValueError):
        layout_from_names("A, B")


def test_no_hardcoded_category_literals_left(self):
    hits = [
        str(f)
        for f in Path("src/notebooklm_batch_studio").rglob("*")
        if f.suffix in {".py", ".js", ".html"}
        and f.name != "study_layout.py"
        and re.search(r"0[12] (Material|Handout)\b(?!s)", f.read_text(encoding="utf-8"))
    ]
    self.assertEqual(hits, [])
```

- [x] **Step 2–4:** 失敗 → 實作 → `uv run python -m unittest discover -s tests` 通過（既有測試若斷言 `01 Material` 為講次來源，改斷言新行為，commit 訊息註明）
- [x] **Step 5:** Commit `-m "feat(domain): configurable plural study categories with aliases; remove hardcoded names"`

### Task 4: 集中 DATA_DIR 路徑、移除 `load_config()` 後備、安裝建立 study／scratch

**Files:**
- Modify `config/settings.py`；`.env.example`（`STUDY_CATEGORIES=` 範例）
- Modify 寫死路徑處：`adapters/gemini/browser_session.py:165,364`、`services/notes/gemini_auth_service.py:78`、`adapters/note_driver_factory.py:98`（三處 `state/gemini_profile` 改用 `config.gemini_profile_dir`）、`adapters/gemini/web_driver.py:60`、`services/course_settings.py:441`、`services/notes/note_pipeline_service.py:97-98`、`services/notes/note_paths.py:94`
- Modify 後備處（改為必填 `config: AppConfig`）：`services/notes/gemini_auth_service.py:75`、`adapters/notebooklm/client.py:55`、`adapters/ollama/client.py:37`、`adapters/gemini/browser_session.py:160`、`services/artifact_runner.py:107`、`services/course_settings.py:76`、`services/orchestrator.py:81`
- Modify 安裝：`scripts/agentctl.py setup` 呼叫的專案初始化（找出建立 `DATA_DIR` 子資料夾的位置；若無，於 `entrypoints/cli.py` 加 `init-data` 子命令並由 setup 呼叫）建立 `study/`、`scratch/<五種>/`
- Test `tests/test_settings_paths.py`

**Interfaces — Produces（`AppConfig`）:** `gemini_profile_dir`、`diagnostics_dir`、`deleted_dir`、`prompt_override_dir`、`notes_state_dir`、`scratch_kind_dir(kind: str) -> Path`（`kind` 限五種，否則 `ValueError`）、`study_categories: str = ""`、`study_layout: StudyLayout`（屬性）

- [x] **Step 1: 失敗測試**：（1）所有新屬性 `is_relative_to(cfg.data_dir)`；（2）`scratch_kind_dir("../x")` 與 `("other")` 皆 `ValueError`；（3）`src/` 中 `config/` 以外沒有 `(data_dir|state_dir|scratch_dir|output_dir|input_dir)\s*/\s*"`；（4）`entrypoints/`、`config/` 以外沒有 `load_config()`；（5）`init-data` 在空資料夾建立 `study/` 與 `scratch/literature|notes|outputs|uploads|unarchived`，重跑不報錯。
- [x] **Step 2–4:** 失敗 → 實作（`load_config()` 只在 CLI、api、mcp_server 入口呼叫一次）→ `uv run python -m unittest discover -s tests` 通過（補上必填 config 的測試一律用 tmp `AppConfig`）
- [x] **Step 5:** Commit `-m "refactor(config): centralize data paths, drop implicit load_config, init study/scratch"`

### Task 5: 資料庫欄位、record-only、文獻分類預設

**Files:** Create `alembic/versions/20261125_<rev>_course_status_and_course_no.py`（`down_revision="85aedf6f2f6f"`）；Modify `adapters/db/models.py`（`CourseRecord.status String(20) default/server_default "active"`、`course_no String(50) default ""`；`LiteratureItemRecord.target_category` server_default 改 `"01 Materials"`，既有資料不改）、`domain/models.py`（`CourseStatus`、`Course.status`、`Course.course_no`、`ProfileName.RECORD_ONLY = "record-only"`）、`adapters/db/repository.py`（新欄位；`list_courses(status: CourseStatus | None = None)`）、`services/job_planner.py:19`（`RECORD_ONLY: []`）；Test `tests/test_course_lifecycle.py`

- [x] **Step 1: 失敗測試**：status/course_no 寫入讀回；`list_courses(status=ARCHIVED)` 過濾；`generate_jobs_for_course(record_only_course) == []`；舊文獻列 `target_category="01 Material"` 讀回後 `DEFAULT_LAYOUT.role_of(...) == MATERIALS`。
- [x] **Step 2–4:** 失敗 → 實作 → `uv run alembic upgrade head && uv run alembic check` 輸出 `No new upgrade operations detected.`；測試通過
- [x] **Step 5:** Commit `-m "feat(db): course status, course number, record-only profile, plural literature default"`

### Task 6: 讓舊佈局退場（所有讀寫改走課程的 study 資料夾）

**Files:**
- Modify `services/source_manager.py:340,359`、`services/qa_notes_service.py:124,377,429`（上傳 PDF 改存 `<HANDOUTS>/_uploaded/`；課程沒有 `study_dir` 時存 `scratch/uploads/<code>/`）
- Modify `services/study_service.py:210-213`（閃卡只在 `resolve_course_output_root(..., course.study_dir)` 下找，刪掉跨課程 glob）
- Modify `services/orchestrator.py:82`（`CourseReporter` 依課程 output root 寫 `summary.md/html`）
- Modify `services/course_settings.py:443`（刪除課程時也處理 `03 Notes/NotebookLM` 以外不動；見 Task 11）
- Modify `services/folder_browser.py:47-83`、`entrypoints/http/settings.py:228`、`entrypoints/mcp_studio_tools.py:359`（第一個捷徑改為 `study_root_dir`，第二個 `scratch_dir`；`input/courses` 存在時列為「舊課程資料夾（待整併）」）
- Test `tests/test_old_layout_retired.py`

- [x] **Step 1: 失敗測試**

```python
def test_flashcards_never_read_another_course(self):
    # 115-1_CP30000 與 115-1_CP31000 都有 03 Notes/NotebookLM/03_x/flashcards.json，內容不同
    self.assertEqual(study.get_lecture_flashcards("115-1_CP30000", 3)[0]["front"], "A-front")


def test_uploads_land_in_handouts(self):
    out = svc._save_uploaded_base64_pdf("115-1_CP30000", "x.pdf", b64)
    self.assertTrue(out.is_relative_to(course_dir / "02 Handouts" / "_uploaded"))
    self.assertFalse((cfg.courses_input_dir).exists())


def test_folder_browser_shortcuts(self):
    names = [e["path"] for e in browse_folders(None, cfg)["folders"][:2]]
    self.assertEqual(names, [str(cfg.study_root_dir.resolve()), str(cfg.scratch_dir.resolve())])


def test_no_new_writes_to_old_layout(self):
    writers = [
        str(f)
        for f in Path("src/notebooklm_batch_studio").rglob("*.py")
        if re.search(r"courses_(input|output)_dir\s*/", f.read_text(encoding="utf-8"))
    ]
    self.assertEqual(
        writers,
        [
            "src/notebooklm_batch_studio/services/study_migration.py",
            "src/notebooklm_batch_studio/services/legacy_consolidation.py",
        ],
    )
```

（`browse_folders` 簽章改為 `browse_folders(path: str | None, config: AppConfig, home: Path | None = None)`）

- [x] **Step 2–4:** 失敗 → 實作 → 全部測試通過
- [x] **Step 5:** Commit `-m "fix(layout): retire input/output course folders, scope flashcards to their course"`

## Phase 1：學期樹、本學期新課程、監看與歸檔

### Task 7: `StudyLibraryService`（掃描、只登錄不生成、手動登錄）

**Files:** Create `services/study_library.py`；Modify `services/course_parser.py`（`scan_course_directory(course_dir: Path, custom_code: str | None = None, term: str = "") -> Course`，既有呼叫端 `course_onboarding.py:77,362,416` 不變；填 `course_no`、`term`、`subject=name`、`study_dir`、`code=make_course_code(...)`）；Test `tests/test_study_library.py`

**Interfaces — Produces:**
- `CourseCandidate(term, folder, code, name, lecture_count, registered)`、`TermEntry(term, courses: list[CourseCandidate], others: list[str])`
- `StudyLibraryService(config, course_repo)`：`.scan() -> list[TermEntry]`、`.register(codes: list[str], archive: bool = True) -> list[dict[str, Any]]`、`.register_folder(term: str, folder: str, course_no: str) -> dict[str, Any]`（給 `專題` 等非標準資料夾）

- [ ] **Step 1: 失敗測試**：掃描回 `["113-1","115-1"]`、`115-1` 課程 `["115-1_CP30000"]`、others `["Course Outline","Holland學習單.docx","專題"]`；register 後 `profile=RECORD_ONLY`、`status=ARCHIVED`、`term="113-1"`、無工作、重複登錄回 `{"skipped": "already registered"}`；重修兩學期 study_dir 不同；`register_folder("115-1","專題","PROJ1151")` 得代碼 `115-1_PROJ1151`、課名 `專題`。
- [ ] **Step 2–4:** 失敗 → 實作（不呼叫 `enqueue_course_artifacts`、不碰 NotebookLM）→ 通過
- [ ] **Step 5:** Commit `-m "feat(study): scan study tree by term, register past courses record-only"`

### Task 8: 本學期新增課程落在 study 樹；課本可選擇作為來源

**Files:** Modify `services/course_onboarding.py:400-456`（`_register_single_course_folder`：資料夾在 `study_root_dir` 外時，需 `term`、`course_no`、`name`，複製 PDF 到 `study/<term>/<課號資料夾>/02 Handouts/` 後再掃描；在 study 樹內則直接用）、`entrypoints/static/studio-wizard.js`（加學期、課號欄位，預設從資料夾名解析）、`services/job_planner.py`（`generation_options["materials_as_source"]` 為真時把 `01 Materials` 的 PDF 列為整門課來源）；Test `tests/test_study_library.py`（追加）

- [ ] **Step 1: 失敗測試**：外部資料夾 `~/tmp/Downloads/團諮` 加入 → 檔案出現在 `study/115-1/CP__30000-團體諮商/02 Handouts/`、原資料夾不變；study 內資料夾加入 → 不複製；`materials_as_source=False` 時課本不上傳。
- [ ] **Step 2–4:** 失敗 → 實作 → 通過
- [ ] **Step 5:** Commit `-m "feat(courses): new courses are placed in the study tree; optional textbook source"`

### Task 9: 監看 study 樹、匯入筆記本進學期、Scratch 種類

**Files:** Modify `services/watcher.py`（`CoursePdfEventHandler(watch_root, resolve_course, on_pdf_detected)`）、`entrypoints/cli.py:241`（監看 `study_root_dir`，以 DB `study_dir` 前綴對應課程，只收 HANDOUTS 角色 PDF）、`services/reverse_import.py`（`ReverseImportOptions` 加 `term: str`（必填）、`course_no: str = ""`、`record_only: bool = True`；來源存 `study/<term>/<課號資料夾>/02 Handouts/`、產出 `03 Notes/NotebookLM`；`profile=RECORD_ONLY`、`status=ARCHIVED` 當 `record_only`）、`entrypoints/http/reverse_import.py:30`、`entrypoints/mcp_qa_notes.py:193`、`services/literature/*`、`services/notes/note_paths.py`（未歸檔改 `scratch_kind_dir(...)`）；Test `tests/test_study_library.py`（追加）

- [ ] **Step 1: 失敗測試**：新 `02 Handouts/w2.pdf` 觸發；`04 Homework/hw.pdf` 與 `專題/x.pdf` 不觸發；反向匯入結果在 `study/113-2/` 下、`output/imported_sources` 不存在、課程為 record-only／archived；文獻與筆記未歸檔路徑分別為 `scratch/literature`、`scratch/notes`。
- [ ] **Step 2–4:** 失敗 → 實作 → 通過
- [ ] **Step 5:** Commit `-m "feat(study): watch study tree, import notebooks into terms, scratch kinds"`

### Task 10: 通用歸檔／撤銷歸檔

**Files:** Create `services/filing.py`；Modify `services/literature/archive.py`（改呼叫 `FilingService`）；Test `tests/test_filing.py`

**Interfaces — Produces:**
- `FilingService(config, course_repo)`：
  - `.list_unfiled(kind: str | None = None) -> list[dict[str, str]]`
  - `.file(path: Path, target: FilingTarget) -> Path`，`@dataclass(frozen=True) class FilingTarget: course_code: str; role: CategoryRole; subfolder: str = ""`
  - `.unfile(path: Path) -> Path`（移到 `scratch/unarchived/<課程代碼>/`）
- 來源必須在 `scratch_dir` 或某課程 study 資料夾內（`ensure_within_roots`）；目的地同名 → 加 `-2`、`-3` 後綴，不覆寫；`NOTES` 角色只能放進子資料夾，不得覆寫使用者檔案。

- [ ] **Step 1: 失敗測試**：scratch 檔歸到 `05 Assignments/期中` 後在新位置、scratch 不再有；同名不覆寫；`unfile` 回到 `scratch/unarchived/115-1_CP30000/`；`/etc/hosts` 拒絕（`PathSafetyError`）；文獻既有 `import_to_course`／`unarchive_item` 測試照過。
- [ ] **Step 2–4:** 失敗 → 實作 → 通過
- [ ] **Step 5:** Commit `-m "feat(study): generic file/unfile between scratch and course categories"`

## Phase 2：課程生命週期

### Task 11: 封存／恢復、改代碼、刪除改為建議封存

**Files:** Create `adapters/db/course_identity_repo.py`、`services/course_lifecycle.py`；Modify `adapters/db/queue_repository.py:99,404,464`（排除 `status=="archived"`，與排除 paused 同處）、`services/study_plan_service.py`（Today、到期複習略過封存課程）、`services/course_settings.py:427-450`（刪除回傳加 `"learning_records_removed": {...}` 筆數；HTTP/MCP 的刪除說明改為先建議封存）；Test `tests/test_course_lifecycle.py`（追加）

**Interfaces — Produces:**
- `CourseIdentityRepository(session).rename_code(old: str, new: str) -> dict[str, int]`：單一交易；複製 `courses` 列 → 更新 `lectures`、`artifact_jobs`、`quiz_attempts`、`quiz_mistakes`、`study_progress`、`review_items`、`explanations`、`key_points`（含 `id` 的 `"<code>:<no>"`）、`tutor_messages`、`course_qa_notes`、`literature_items` → 刪舊列；回每表筆數
- `CourseLifecycleService(course_repo, queue_repo, identity_repo, config)`：`.archive(code)`、`.restore(code)`、`.rename(old, new, dry_run=True) -> dict[str, Any]`；`rename` 另外同步：`course.toml` 的 `code`、`ui_preferences` 中值等於舊代碼的 `course` 鍵、`notes_state_dir/<old>.json` 與 pause 檔、`scratch/notes/<old>/`、`03 Notes/QA_Notes/*.md` frontmatter `course_code`；`notebook_id` 與遠端標題不變；新代碼已存在或有 `running` 工作 → `ValueError`

- [ ] **Step 1: 失敗測試**：rename dry-run 不變更、apply 後 11 表與上述 5 種檔案皆改到新代碼、舊代碼查不到；running／已存在拒絕且全部不變；封存後 `claim_next_job` 回 None、恢復後可取得；封存課程不出現在 Today；刪除課程回傳 `learning_records_removed["quiz_attempts"] == 1`。
- [ ] **Step 2–4:** 失敗 → 實作 → 通過
- [ ] **Step 5:** Commit `-m "feat(courses): archive/restore, safe course-code rename, deletion reports lost records"`

## Phase 3：學習紀錄、三入口、登入狀態

### Task 12: `LearningRecordService`

**Files:** Create `services/learning_record.py`；Test `tests/test_learning_record.py`

**Interfaces — Produces:**
- `CategoryFiles(role, files: list[str])`、`CourseRecordView(code, name, term, status, categories, stats: dict[str, int | float], artifacts: list[dict[str, str]])`、`TermRecordView(term, courses, others)`
- `stats` 鍵：`lectures`、`artifacts_done`、`quiz_attempts`、`quiz_best_score`、`mistakes_open`、`qa_notes`、`literature`、`notestudio_notes`、`study_days`、`study_minutes`、`memory_strength_avg`（後三者來自 `LearningRepository.activity_times` 與 `memory_signals` 經 `domain/memory_model`）
- `artifacts`：該課程 `artifact_jobs` 已完成項目（講次、類型、相對路徑）
- `@dataclass(frozen=True) class RecordRepos: queue_repo; study_repo; learning_repo; qa_repo; literature_repo`
- `LearningRecordService(config, course_repo, repos: RecordRepos)`：`.build(term: str | None = None) -> list[TermRecordView]`、`.export_markdown(term=None) -> str`、`.export_pdf(term: str | None, out: Path) -> Path`（`render_markdown_to_pdf`）
- 檔案清單：遞迴、排除隱藏檔；NoteStudio 筆記與筆記狀態從檔案與 `notes_state_dir` 讀；未登錄的課程資料夾也列出（`status="unregistered"`）；學期層 `others` 照列

- [ ] **Step 1: 失敗測試**：依學期排序；`02 Handouts/slides.pptx`、`05 Assignments/期中/報告.pdf` 出現在 files；`stats["quiz_attempts"]==1`、`study_days>=1`；未登錄課程 `status=="unregistered"`；Markdown 以 `# 學習紀錄` 開頭並含 `## 115-1`、`### CP30000 團體諮商`；`export_pdf` 產生 `%PDF` 開頭檔案。
- [ ] **Step 2–4:** 失敗 → 實作 → 通過
- [ ] **Step 5:** Commit `-m "feat(record): cross-term learning record with study time, memory strength, MD/PDF export"`

### Task 13: HTTP、MCP、網頁三入口

**Files:** Create `entrypoints/http/study_library.py`（掛 `api.py`）、`entrypoints/mcp_study_library.py`（由 `mcp_extensions` 註冊）、`entrypoints/static/studio-record.js`；Modify `index.html`（`data-view="record"` 頁、文獻分類下拉改動態）、`studio-study-panels.js:20-30`、`studio-app.js:160-170`（課程選單依 `term` 分組、預設隱藏封存、可切換）、`services/course_onboarding.py:234-260`（摘要加 `term`、`course_no`、`status`）；新工具的未確認回應一律用 `entrypoints/mcp_confirm.py::confirm_warning`（Antigravity `9d6ef12` 已建立）；Test `tests/test_study_library_api.py`

| HTTP | MCP | 會改資料 |
|---|---|---|
| `GET /api/study/layout` | `get_study_layout` | 否 |
| `GET /api/study/library` | `scan_study_library` | 否 |
| `POST /api/study/library/register` `{codes, archive}` | `register_past_courses(codes, archive=True, confirm=False)` | 是 |
| `POST /api/study/library/register-folder` `{term, folder, course_no}` | `register_study_folder(term, folder, course_no, confirm=False)` | 是 |
| `GET /api/study/unfiled?kind=` | `list_unfiled(kind=None)` | 否 |
| `POST /api/study/file` `{path, course_code, role, subfolder}`／`POST /api/study/unfile` `{path}` | `file_item(path, target, confirm=False)`／`unfile_item(path, confirm=False)` | 是 |
| `POST /api/courses/{code}/archive`、`/restore` | `set_course_archived(code, archived, confirm=False)` | 是 |
| `POST /api/courses/{code}/rename` `{new_code, dry_run}` | `rename_course_code(code, new_code, dry_run=True, confirm=False)` | 是 |
| `GET /api/study/record?term=`、`GET /api/study/record/export?term=&format=md|pdf` | `get_learning_record(term=None)`、`export_learning_record(term=None, format="md")` | 否 |

- [ ] **Step 1: 失敗測試**：每列 HTTP 200／MCP 名稱存在；會改資料的 MCP 未確認回 `confirmed: false`；`/api/courses` 列含 `term`、`course_no`、`status`；非法代碼回 400／404；掃描全部 MCP 工具，凡有 `confirm` 參數者在 `confirm=False` 時回應都含 `"confirmed": false`。
- [ ] **Step 2–4:** 失敗 → 實作（前端一律 `escHtml`／`jsAttr`，`node --check`）→ 通過
- [ ] **Step 5: 瀏覽器驗證**：`preview_start web-verify`；學習紀錄頁列出學期、課程選單依學期分組、封存切換、匯出 MD／PDF 可下載；console 無錯、無 4xx/5xx；截圖
- [ ] **Step 6:** Commit `-m "feat(study): HTTP/MCP/web for study library, filing, lifecycle, learning record"`

### Task 14: 三組登入狀態一覽

**Files:** Create `services/auth_status.py`；Modify `entrypoints/http/system.py`（`GET /api/system/sign-ins`）、MCP `get_sign_in_status`、設定頁顯示、`README.md` 與 `docs/architecture/ARCHITECTURE.md` §4 說明三組登入（NotebookLM：`notebooklm_home`；Gemini 網頁：`gemini_profile_dir`；文獻：`literature_browser_profile_dir`）；Test `tests/test_auth_status.py`

**Interfaces — Produces:** `sign_in_status(config: AppConfig, gemini_auth: GeminiAuthService) -> list[dict[str, str]]`，每列 `{"name", "location", "state": "ready|missing|expired", "how_to_sign_in"}`；Gemini 列直接用 `GeminiAuthService.check_auth_status(live_check=False)`（Antigravity `3976c94`，入口 `/api/notes/gemini/login`）；NotebookLM 與文獻只檢查檔案／資料夾是否存在，不讀 cookie 內容。

- [ ] **Step 1–4:** 測試三種狀態（tmp 中建立／不建立對應資料夾）→ 實作 → 通過
- [ ] **Step 5:** Commit `-m "feat(system): sign-in status overview for NotebookLM, Gemini web and library"`

## Phase 4：既有資料整併與收尾

### Task 15: 一次性整併工具（dry-run 預設）

**Files:** Create `services/legacy_consolidation.py`；Modify `entrypoints/cli.py`（`consolidate --dry-run|--apply --map OLD=NEW --folder OLD=NEW_FOLDER --assign PATH=CODE:ROLE[/SUB]`）；Test `tests/test_legacy_consolidation.py`

**Interfaces — Produces:** `plan_consolidation(config: AppConfig, request: ConsolidationRequest) -> list[ConsolidationStep]`、`apply_consolidation(config, steps) -> dict[str, int]`；`ConsolidationStep(action: Literal["move","merge","rename_code","rename_folder","import_notes","inventory"], source: str, target: str, note: str)`

涵蓋：
1. `input/courses/<舊資料夾>` 的 PDF → `study/<學期>/<課號資料夾>/02 Handouts/`；
2. 課程資料夾改名為校方命名（`study/115-1/生涯諮商` → `study/115-1/CP__31000-生涯諮商與實務`），同步 `courses.source_dir`、`study_dir`、`artifact_jobs.output_file` 前綴（比照 `study_migration_repo.apply_course_migration`）；
3. 單數分類資料夾內容併入複數名（同名檔加後綴、不覆寫），空資料夾保留不刪；
4. `rename_code`（呼叫 Task 11）；
5. note-studio 筆記 → `03 Notes/NoteStudio/`（`import_legacy_notes`）；
6. 任意路徑指派（例 `midterm-submission/` → `<課程>:ASSIGNMENTS/期中專題`）；
7. `deleted/` 只做 inventory：每個子資料夾的大小、日期、是否含 `.json`／`.md` 學習資料，不搬不刪。

- [ ] **Step 1–4:** 測試 dry-run 不改任何檔案與 DB；apply 後來源→目的地可由報告追溯；同名不覆寫；DB 路徑前綴已更新且 `GET /api/artifacts/<新代碼>/view/...` 200 → 實作 → 通過
- [ ] **Step 5:** Commit `-m "feat(cli): dry-run-first consolidation of legacy data into the study tree"`

### Task 16: 在使用者電腦上整併（每步需使用者確認）

- [ ] **Step 1:** 請使用者確認 Q1–Q5（對照表、`midterm-submission` 歸屬、`deleted/` 政策）；檢查 `deleted/115-1-20261112-182701` 內容（`ls -R`、檔案類型統計），回報是否為被誤刪的 `心理學研究法` 資料，由使用者決定是否還原。
- [ ] **Step 2:** 經使用者同意，在 `.env` 加 `LEGACY_NOTE_STUDIO_DIR=/Users/limchinkun/Desktop/projects-data/note-studio/output/courses`。
- [ ] **Step 3:** `uv run notebooklm-batch-studio consolidate --dry-run …` → 貼出計畫表 → 使用者同意後 `--apply`；貼出結果。
- [ ] **Step 4:** 使用者自行從備份複製 113-1～114-2 到 `DATA_DIR/study/`；`GET /api/study/library` 確認列出 → 使用者勾選 → `register(archive=True)`。
- [ ] **Step 5:** 證據：`notebooklm-batch-studio status`、`GET /api/study/record` 學期數與課程數、NoteStudio 筆記數（應 ≥ 109）、`GET /api/system/sign-ins`、瀏覽器截圖。

### Task 17: 收尾、文件、驗收

**Files:** `docs/architecture/ARCHITECTURE.md`（新服務、資料流、§4 安全與資料位置）、`docs/specs/014-…`（勾選驗收）、`docs/specs/001-batch-generation.md`、`docs/specs/010-user-end-to-end-workflow.md`、`docs/standards/PROJECT_RULES.md`（再次核對）、`README.md`（更新方法：`git pull` → `uv sync` → `uv run alembic upgrade head` → `init-data` → 需要時 `consolidate --dry-run`；核心規則 14）、`scripts/demo/demo-data.js`（假資料加 `term`、`course_no`、`status`，展示學期分組與學習紀錄）

- [ ] **Step 1:** 更新上述文件；`uv run python scripts/build_demo.py`
- [ ] **Step 2:** `python3 scripts/agentctl.py check` 結束碼 0、`uv run python -m unittest discover -s tests -v` 全過、`python3 scripts/agentctl.py scan` 無新警告、`python3 .agents/skills/project-auditor/scripts/audit_project_integrity.py` 無新增 TODO
- [ ] **Step 3:** Task 0 登錄的 known-issue 逐項改為 resolved 並填防回歸測試名稱；CHANGELOG 補 TASK-033、ISSUE-042..044；11 條「待實機」驗收項目列給使用者實機檢查
- [ ] **Step 4:** `agentctl task done`、Commit；使用者說「收工」時依 `session-closeout` 建立對話紀錄（含今天兩段對話）；push 前徵得同意

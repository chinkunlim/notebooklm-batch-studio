# SPEC-014：學習資料庫統一與完整學習紀錄（Study Library & Learning Record）

- **狀態**：Approved <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-24
- **相關任務 / ADR**：TASK-035 / ADR-014（部分修訂 ADR-011）

## 1. 目標

讓 `DATA_DIR/study/<學期>/<課程>/<分類>` 成為唯一的課程資料結構、`DATA_DIR/scratch/<種類>/` 成為唯一的未歸檔暫存區，課程以「學期＋課號」識別（`<學期>_<課號>`，例如 `115-1_CP30000`），可一次掃描並登錄過去學期（`113-1` 起）的課程而不消耗生成額度（`record-only` + `archived`），同時提供跨學期、可匯出 Markdown／PDF 的完整學習紀錄，並徹底清掉舊 `input/courses`、`output/courses` 佈局與路徑／身分／紀錄缺口。

成功的樣子：
- 所有本學期與舊學期課程統一位於 `DATA_DIR/study/<學期>/<課程資料夾>/<分類>`，校方命名如 `CP__30000-團體諮商` 與 `YY__5061AA-體育 (三)_超慢跑 AA` 皆正確解析且跨學期重修互不衝突。
- 過去學期課程可透過學習資料庫掃描一鍵登錄為 `record-only`／`archived`，不排程生成、不碰遠端額度，仍完整納入學習紀錄統計與匯出。
- 未歸檔檔案集中於 `DATA_DIR/scratch/<種類>/`，並可在課程分類間安全歸檔與撤銷歸檔。
- 使用者可在 Web、HTTP API 與 MCP 三入口檢視完整學習紀錄（教材、產出、NoteStudio、問答筆記、測驗與錯題、文獻、作業報告、讀書時間、記憶強度）並匯出 Markdown 或 PDF。

## 2. 使用情境

- **學生／使用者整理跨學期學習庫**：從雲端備份複製 `113-1`、`114-1` 等舊學期資料夾到 `DATA_DIR/study/`，透過掃描一鍵登錄為 `record-only` 課程（包含 `專題` 等非標準資料夾手動填課號登錄），並使用學習紀錄總覽與匯出功能回顧整段大學／研究所學習歷程。
- **本學期新增課程與即時監看**：透過挑選器或外部資料夾加入新課時，資料自動落在 `DATA_DIR/study/<學期>/<課號資料夾>/02 Handouts/`；目錄監看器只監看 `study_root_dir` 下的 `HANDOUTS` 角色 PDF，不誤觸作業或教材。
- **未歸檔檔案與文獻整理**：下載的文獻、暫存筆記、上傳檔與撤銷歸檔退回的檔案統一落於 `DATA_DIR/scratch/<種類>/`，可隨時歸檔至指定課程分類與子資料夾，或退回 `scratch/unarchived/<課程代碼>/`。
- **AI Agent（Claude Code / Antigravity / Open WebUI）**：透過 MCP 工具與 OpenAPI 路由查詢學習庫、歸檔、管理封存與改代碼、查詢與匯出學習紀錄；所有會修改資料或移動檔案的 MCP 工具都要求 `confirm=True`。

## 3. 需求

### 使用者已確認需求（2026-11-24）

1. 學習資料只放在 `DATA_DIR/study/`（例如 `projects-data/notebooklm-batch-studio/study/`）；iCloud 等雲端只做備份，程式不讀寫雲端資料夾。
2. 結構固定為 `study/<學期>/<課程資料夾>/<分類>/[子資料夾…]`，學期格式如 `113-1`…`115-1`。
3. 課程資料夾命名支援校方格式：`CP__30000-團體諮商`、`GC__68210-和 AI 一起寫程式`、`YY__5061AA-體育 (三)_超慢跑 AA`（保留空白、括號、全形字與底線）。
4. 學期資料夾允許非課程資料夾（如 `Course Outline`、`專題`）與散檔（`.epub`、`.md`、`.docx`），掃描時列出但不自動當成課程，並支援手動登錄非標準資料夾。
5. 五個標準分類（複數預設、支援單數別名）：
   - `01 Materials`（別名 `01 Material`）：課本與文獻（預設不上傳為講次；課程選項 `materials_as_source` 開啟時才作整門課來源）。
   - `02 Handouts`（別名 `02 Handout`）：老師給的 PDF／PPT（含子資料夾；**只有 PDF 成為講次**，`.pptx`/`.docx` 只列入學習紀錄）。
   - `03 Notes`：專案生成的筆記與個人隨筆（AI 產出落在 `NotebookLM/`、`NoteStudio/`、`QA_Notes/`，其餘使用者隨筆不得移動或覆寫）。
   - `04 Homework`：作業。
   - `05 Assignments`：期中／期末報告（支援子資料夾）。
6. `scratch/` 與 `study/` 同層，存放尚未歸檔的結果與撤銷歸檔退回的檔案；子目錄種類固定為 `literature`、`notes`、`outputs`、`uploads`、`unarchived`。
7. 可開啟舊學期課程，彙整並呈現完整學習紀錄（教材、NotebookLM 產出、NoteStudio 筆記、問答筆記、測驗與錯題、文獻、作業報告、讀書時間、記憶強度），支援匯出 Markdown 與 PDF。

### 必須遵守之全域約束 (Must / Global Constraints)

- **課程代碼與安全**：代碼格式為 `<學期>_<課號>`（如 `115-1_CP30000`）；課號取 `__` 或 `_` 兩側英數字相接轉大寫（`CP__30000` → `CP30000`、`YY__5061AA` → `YY5061AA`）；必須通過 `domain/path_safety.validate_path_segment`。
- **分類彈性**：預設複數名 `01 Materials`…`05 Assignments`，可透過 `.env` 的 `STUDY_CATEGORIES`（須剛好 5 個逗號分隔名稱）覆寫；讀取時合併別名，建立目錄時不重複建置。
- **路徑集中與不可變**：所有 `DATA_DIR` 子路徑集中由 `AppConfig` 提供；`entrypoints/` 與 `config/` 以外禁止隱式 `load_config()`；任何新寫入不得落在 `input/courses` 或 `output/courses`。
- **封存與安全刪除**：舊學期課程預設 `profile="record-only"`、`status="archived"`；封存課程不進工作佇列、Today 與到期複習，課程選單預設隱藏；課程生命週期採 Google Classroom 模式（`active → archived → 刪除`），未封存課程一律拒絕刪除並提示「請先封存課程」，刪除只移除資料庫並回報遺失學習紀錄筆數，**絕不刪除或移動 `study/` 內任何檔案**（僅可搬移舊佈局 `output/courses/<code>` 與 `needs_review/<code>_*` 至 `deleted/`）。
- **三入口一致與確認防護**：所有新服務同時提供 HTTP、MCP 與 Web UI；會新增、移動、封存或改寫資料的 MCP 工具皆帶 `confirm: bool = False`，未確認回傳 `{"confirmed": false, "warning": "..."}`（經 `entrypoints/mcp_confirm.py::confirm_warning`）。

### 不做 (Out of scope)

- SPEC-001「完成時 macOS 通知」另案處理，不納入本規格。
- 11 條需實機連線 Gemini Notebook 的驗收項目由使用者實機驗證。
- 程式不自動讀寫 iCloud 路徑，亦不自動刪除 `DATA_DIR/deleted/`。

## 4. 介面 / API（三入口對照）

| HTTP 路由 | MCP 工具 | 會改資料 | 說明 |
|---|---|---|---|
| `GET /api/study/layout` | `get_study_layout` | 否 | 取得目前 5 個學習分類名稱與角色對應 |
| `GET /api/study/library` | `scan_study_library` | 否 | 掃描 `DATA_DIR/study/` 學期樹與待登錄課程 |
| `POST /api/study/library/register` (`{codes, archive}`) | `register_past_courses(codes, archive=True, confirm=False)` | 是 | 批次登錄掃描到的課程（`record-only`，不排生成） |
| `POST /api/study/library/register-folder` (`{term, folder, course_no}`) | `register_study_folder(term, folder, course_no, confirm=False)` | 是 | 手動登錄非標準資料夾（如 `專題`） |
| `GET /api/study/unfiled?kind=` | `list_unfiled(kind=None)` | 否 | 列出 `scratch/<種類>/` 未歸檔檔案 |
| `POST /api/study/file` (`{path, course_code, role, subfolder}`) | `file_item(path, target, confirm=False)` | 是 | 將檔案安全歸檔到課程分類（同名加 `-2` 不覆寫） |
| `POST /api/study/unfile` (`{path}`) | `unfile_item(path, confirm=False)` | 是 | 將檔案撤銷歸檔退回 `scratch/unarchived/<課程代碼>/` |
| `POST /api/courses/{code}/archive` | `set_course_archived(code, archived=True, confirm=False)` | 是 | 封存課程（排除佇列與 Today） |
| `POST /api/courses/{code}/restore` | `set_course_archived(code, archived=False, confirm=False)` | 是 | 解除封存，恢復為 `active` |
| `POST /api/courses/{code}/rename` (`{new_code, dry_run}`) | `rename_course_code(code, new_code, dry_run=True, confirm=False)` | 是 | 交易式安全改代碼（預設 dry-run） |
| `GET /api/study/record?term=` | `get_learning_record(term=None)` | 否 | 取得跨學期或單學期完整學習紀錄 JSON |
| `GET /api/study/record/export?term=&format=md\|pdf` | `export_learning_record(term=None, format="md")` | 否 | 匯出學習紀錄為 Markdown 或 PDF |
| `GET /api/system/sign-ins` | `get_sign_in_status` | 否 | 檢視 NotebookLM、Gemini 網頁、圖書館三組登入狀態 |

> **前期查收與基礎防線確認（2026-11-24）**：本規格承接已驗收之前置修正 commits `3976c94`（Gemini Web 登入三入口，`ISSUE-053`）、`13dff45`（啟動關閉殘留文獻工作，`ISSUE-054`）、`9d6ef12`（統一 57 支 MCP 工具 `confirm=False` 回應格式）與 `8ab99cb`（規格/ADR/任務溯源稽核）。

## 5. 驗收標準（BDD Given / When / Then 場景與對應測試）

### 5.1 課程身分與學期碼（Task 2）
- [ ] **場景 1（校方課號解析保留完整課名）**
  - **Given** 資料夾名稱為 `CP__30000-團體諮商` 與 `YY__5061AA-體育 (三)_超慢跑 AA`
  - **When** 呼叫 `parse_course_folder`
  - **Then** 回傳 `CourseFolderInfo(course_no="CP30000", name="團體諮商", is_course=True)` 與 `CourseFolderInfo(course_no="YY5061AA", name="體育 (三)_超慢跑 AA", is_course=True)`
  - 對應測試：`tests/test_course_identity.py::test_parses_school_course_folders`
- [ ] **場景 2（非課程資料夾不誤判）**
  - **Given** 資料夾名稱為 `Course Outline`、`專題`、`115-1`、`.DS_Store`、`生涯諮商`
  - **When** 呼叫 `parse_course_folder`
  - **Then** 回傳 `is_course == False`
  - 對應測試：`tests/test_course_identity.py::test_non_course_folders`
- [ ] **場景 3（跨學期代碼組合、拆解與標題安全）**
  - **Given** 同一課號 `CP30000` 於 `114-1` 與 `115-1` 修習，及非法字元 `CP/30000`
  - **When** 呼叫 `make_course_code`、`split_course_code`、`notebook_title`
  - **Then** 產生不同代碼 `114-1_CP30000` 與 `115-1_CP30000`、標題 `[CP30000] 團體諮商 (115-1)`，非法路徑拋出 `PathSafetyError`
  - 對應測試：`tests/test_course_identity.py::test_codes`

### 5.2 分類名稱、別名與角色（Task 3）
- [ ] **場景 4（單複數別名合併、非 PDF 不當講次、課本不是講次）**
  - **Given** 課程目錄內同時存在 `02 Handout/a.pdf`、`02 Handouts/sub/b.pdf`、`02 Handouts/c.pptx` 與 `01 Materials/textbook.pdf`
  - **When** 掃描課程目錄與查詢 `CategoryRole.HANDOUTS`
  - **Then** `category_dirs` 合併單複數資料夾；講次只包含 `a.pdf` 與 `b.pdf`（含相對路徑），課本與 `.pptx` 不成為講次
  - 對應測試：`tests/test_study_layout.py::test_singular_and_plural_handouts_merged`、`test_materials_are_not_lectures`
- [ ] **場景 5（補齊目錄不重複建、自訂分類與無硬編碼檢查）**
  - **Given** 已有 `01 Material/` 資料夾；以及以 `STUDY_CATEGORIES` 傳入少於 5 個名稱
  - **When** 執行 `DEFAULT_LAYOUT.ensure_tree`、`layout_from_names` 與原始碼掃描
  - **Then** 不會另外建立重複的 `01 Materials/`；非法長度拋出 `ValueError`；`src/` 除 `study_layout.py` 外無殘留單數寫死分類字面
  - 對應測試：`tests/test_study_layout.py::test_ensure_tree_respects_alias`、`test_role_of_and_custom_names`、`test_no_hardcoded_category_literals_left`

### 5.3 路徑集中與環境隔離（Task 4）
- [ ] **場景 6（集中 `DATA_DIR` 路徑與 `init-data` 冪等初始化）**
  - **Given** 一個空白 `tmp` 目錄建構 `AppConfig`
  - **When** 檢查所有路徑屬性、`scratch_kind_dir` 邊界與執行兩次 `init-data`
  - **Then** 新屬性皆位於 `data_dir` 內；非法種類（`../x`、`other`）拋出 `ValueError`；`src/` 除 `config/` 與 `entrypoints/` 外無 `load_config()` 與硬編碼子路徑；`study/` 與 5 個 `scratch/<kind>/` 皆存在
  - 對應測試：`tests/test_settings_paths.py`

### 5.4 資料庫欄位與舊佈局退場（Task 5 & Task 6）
- [ ] **場景 7（資料庫 `status`/`course_no`、`record-only` 與舊文獻分類相容）**
  - **Given** `status=ARCHIVED`、`course_no` 與 `profile=RECORD_ONLY` 的課程，及舊資料 `target_category="01 Material"`
  - **When** 寫入與查詢 `CourseRepository`、執行 `generate_jobs_for_course`
  - **Then** 可依 `status` 過濾、`RECORD_ONLY` 回傳空工作清單、舊 `"01 Material"` 對應 `CategoryRole.MATERIALS`
  - 對應測試：`tests/test_course_lifecycle.py`
- [ ] **場景 8（閃卡隔離、上傳與瀏覽捷徑切換、不再寫入舊佈局）**
  - **Given** 兩門課程各自於 `study/` 有同編號講次閃卡；透過上傳 base64 PDF；呼叫 `browse_folders(None, cfg)`
  - **When** 查詢閃卡、儲存上傳 PDF、掃描原始碼
  - **Then** 閃卡只讀所屬課程不跨課；上傳落入 `<HANDOUTS>/_uploaded/`；捷徑前兩項為 `study_root_dir` 與 `scratch_dir`；除遷移／整併模組外無程式碼寫入 `courses_input_dir`／`courses_output_dir`
  - 對應測試：`tests/test_old_layout_retired.py`

### 5.5 學習庫掃描、本學期建課、監看、歸檔與生命週期（Task 7–11）
- [ ] **場景 9（掃描學期樹並以 `record-only` 登錄舊課程，支援非標準資料夾）**
  - **Given** `study/` 含 `113-1`、`115-1`（含 `CP__30000-團體諮商`、`Course Outline`、`專題`、`.docx`）
  - **When** 呼叫 `StudyLibraryService.scan()`、`register()`、`register_folder("115-1", "專題", "PROJ1151")`
  - **Then** 正確區分課程與 `others`；登錄後 `profile=RECORD_ONLY`、`status=ARCHIVED`、不產生工作；重複登錄略過；重修兩學期 `study_dir` 各自獨立
  - 對應測試：`tests/test_study_library.py`
- [ ] **場景 10（本學期外部資料夾落入 `study` 樹、課本選用與監看／反向匯入／歸檔）**
  - **Given** 外部暫存資料夾加入課程、設定 `materials_as_source=False`、監看器收到新 PDF、反向匯入指定學期、執行 `FilingService.file/unfile`
  - **When** 執行對應服務
  - **Then** 外部 PDF 複製至 `study/<term>/<folder>/02 Handouts/`；課本不上傳；只有 `02 Handouts` PDF 觸發監看；歸檔防同名覆寫並阻擋越界路徑，撤銷歸檔回到 `scratch/unarchived/<code>/`
  - 對應測試：`tests/test_study_library.py`、`tests/test_filing.py`
- [ ] **場景 11（封存／恢復、改代碼與安全刪除：Task 11 ＋ Google Classroom 生命週期）**
  - **Given（場景 11a：封存排除佇列、Today 與到期複習）** 一門 `active` 課程含有 `pending` 工作、到期複習卡與未完成學習步驟
  - **When** 呼叫 `CourseLifecycleService.archive(code)`，再呼叫 `CourseLifecycleService.restore(code)`
  - **Then** 封存後 `claim_next_job` 回傳 `None`、`count_by_status(runnable_only=True)` 排除該課、課程不出現在 `StudyPlanService.get_today()` 且 `due_reviews(code)` 回空陣列；恢復後 `claim_next_job`、`get_today()` 與 `due_reviews(code)` 皆重新出現該課
  - 對應測試：`tests/test_course_lifecycle.py::CourseArchiveAndRenameTests::test_archive_excludes_queue_today_and_due_reviews_and_restore_reinstates`
  - **Given（場景 11d：改代碼預設 dry-run 不變更資料與檔案）** 一門課程擁有 11 張表資料、`ui_preferences` 與 5 種本機檔案
  - **When** 呼叫 `CourseLifecycleService.rename(old, new)`（預設 `dry_run=True`）
  - **Then** 回傳各表與各檔案預計變更數；資料庫舊代碼與全部檔案內容皆原封不動
  - 對應測試：`tests/test_course_lifecycle.py::CourseArchiveAndRenameTests::test_rename_dry_run_reports_counts_without_changes`
  - **Given（場景 11e：有 `running` 工作或新代碼已存在時拒絕改代碼）** 課程有 `status="running"` 的工作，或目標新代碼已存在於 `courses` 表
  - **When** 呼叫 `CourseLifecycleService.rename(old, new, dry_run=False)`
  - **Then** 拋出 `ValueError`，資料庫與所有本機檔案完全不變
  - 對應測試：`tests/test_course_lifecycle.py::CourseArchiveAndRenameTests::test_rename_refused_on_running_job_or_existing_target`
  - **Given（場景 11f：改代碼成功同步 11 張表、偏好與 5 種檔案，更新 `term`/`course_no`）** 課程 `115-1` 含有 11 張子表資料、`ui_preferences`、`course.toml`、`notes_state_dir/<old>.json` 與 `.pause.json`、`scratch/notes/<old>/`、`03 Notes/QA_Notes/*.md` frontmatter，以及 `notebook_id="nb-keep"` 與既有 `study_dir`
  - **When** 呼叫 `CourseLifecycleService.rename("115-1", "115-1_CP31000", dry_run=False)`
  - **Then** 11 張子表、`ui_preferences` 與 5 種本機檔案全數改為 `115-1_CP31000`；舊代碼查無課程；新課程 `term == "115-1"`、`course_no == "CP31000"`；`notebook_id`、`study_dir`、`source_dir` 與資料夾名稱不變
  - 對應測試：`tests/test_course_lifecycle.py::CourseArchiveAndRenameTests::test_rename_apply_updates_all_11_tables_prefs_and_files`
  - **Given（場景 11g：改代碼中途失敗完整回滾資料庫與已改檔案）** 改代碼已更新資料庫並修改部分檔案後，在後續檔案同步拋出 `OSError`
  - **When** 呼叫 `CourseLifecycleService.rename(old, new, dry_run=False)`
  - **Then** 拋出例外，資料庫整筆交易回滾（舊代碼與 11 張表保留、新代碼不存在），已更動之本機檔案全數還原至改碼前狀態
  - 對應測試：`tests/test_course_lifecycle.py::CourseArchiveAndRenameTests::test_rename_midway_failure_rolls_back_db_and_files`
  - **Given（場景 11h：改代碼一併搬移後備輸出與 `needs_review` 並可 HTTP 200 讀取）** 課程沒有 `study_dir`、於 `output/courses/<old>/` 與 `needs_review/<old>_*` 有檔案，且 `artifact_jobs.output_file` 指向 `needs_review/<old>_*`
  - **When** 執行 `CourseLifecycleService.rename(old, new)`（`dry_run=True` 再 `dry_run=False`）
  - **Then** dry-run 計入 `files.course_output` 與 `files.needs_review`（目標已存在則拒絕）；apply 後兩者皆搬至新代碼、`artifact_jobs.output_file` 更新，且 `GET /api/artifacts/<new>/download/_needs_review/<new>_.../<file>` 回傳 200；中途失敗時兩者皆搬回原處
  - 對應測試：`test_rename_moves_fallback_output_and_needs_review_and_serves_http_200`、`test_rename_midway_failure_rolls_back_fallback_output_and_needs_review`
  - **Given（場景 11i：改代碼改寫筆記 `stitched_path` 暫存路徑但保留 `study_dir` 路徑）** 筆記狀態某章 `stitched_path` 指向 `scratch/notes/<old>/...`（含相對 `<old>/...`），另一章指向 `study_dir/...`
  - **When** 呼叫 `CourseLifecycleService.rename(old, new, dry_run=False)`
  - **Then** 指向 `scratch/notes/<old>/` 的 `stitched_path` 改寫為新代碼且指向實際存在檔案；`study_dir` 路徑維持不變
  - 對應測試：`test_rename_rewrites_scratch_stitched_path_but_keeps_study_dir_path`
  - **Given（場景 11j：筆記生成中或含關聯文獻的文獻鎖持有中拒絕改代碼）** 筆記狀態有章節 `status == "running"`，或 `literature_job.lock` 被持有且課程有 `literature_items`
  - **When** 呼叫 `CourseLifecycleService.rename(old, new)`
  - **Then** 拋出 `ValueError`，資料庫與所有檔案原封不動
  - 對應測試：`test_rename_refused_during_note_generation_or_locked_literature_run`
  - **Given（場景 11b：未封存不能刪除）** 課程狀態為 `active`（含透過 HTTP 與 `confirm=True` 呼叫 MCP `delete_course`）
  - **When** 執行 `delete_course`
  - **Then** 服務拋出 `ValueError("請先封存課程，封存後才能刪除")`、HTTP 回 `409`、MCP 回 `{"confirmed": false, ...}`，資料庫與本機檔案皆不變
  - **Given（場景 11c：刪除不動 `study/` 檔案）** 已封存（`archived`）課程於 `study/<term>/<課程>/03 Notes/NotebookLM/` 與 `03 Notes/` 含有檔案，且可能另有舊佈局 `output/courses/<code>/`
  - **When** 執行 `delete_course`
  - **Then** 移除資料庫課程與 8 張學習紀錄表並回傳 `learning_records_removed`；`study/` 內所有檔案與個人隨筆原封不動，僅舊佈局 `output/courses/<code>/` 移入 `deleted/`
  - 對應測試：`tests/test_course_lifecycle.py`（含 `test_delete_refused_unless_archived`、`test_delete_archived_course_keeps_study_files`、`test_delete_archived_course_moves_only_legacy_output`）

### 5.6 學習紀錄、三入口、登入狀態與整併（Task 12–15）
- [ ] **場景 12（跨學期完整學習紀錄與 Markdown/PDF 匯出）**
  - **Given** 多學期課程（含 `active` 與 `archived` 已封存課程、未登錄校方資料夾 `CP__30000-團體諮商`、非課程資料夾進 `others`、指往 `DATA_DIR` 外的 symlink、`02 Handouts/slides.pptx`、`05 Assignments/期中/報告.pdf`、題庫作答紀錄、`activity_times` 與 `memory_signals`）
  - **When** 呼叫 `LearningRecordService.build(term=None)`、`export_markdown(term=None)`、`export_pdf(term, out_pdf)`
  - **Then** 依學期排序回傳；同時包含 `status="archived"` 與 `status="unregistered"` 課程及學期 `others`；檔案清單只列名稱與相對路徑且不讀檔案內容、略過隱藏檔與 symlink；`stats` 齊全且 `quiz_attempts == 1`、`study_days >= 1`、`memory_strength_avg > 0`；Markdown 以 `# 學習紀錄` 開頭並含 `## 115-1`、`### CP30000 團體諮商`；`export_pdf` 輸出以 `%PDF` 開頭的有效 PDF
  - 對應測試：`tests/test_learning_record.py`
- [ ] **場景 13（HTTP / MCP / Web 三入口、全域 `confirm=False` 與登入狀態總覽）**
  - **Given** 啟動 FastAPI 測試客戶端與掃描全庫 MCP 工具
  - **When** 呼叫 §4 全部端點與工具、以及 `GET /api/system/sign-ins`
  - **Then** 查詢端點回 200；非法代碼回 400/404；全數具 `confirm` 參數之 MCP 工具於 `confirm=False` 回傳 `{"confirmed": false, ...}`；登入狀態正確回報 `ready|missing|expired`
  - 對應測試：`tests/test_study_library_api.py`、`tests/test_auth_status.py`
- [ ] **場景 14（一次性整併工具預設 dry-run 與可追溯報表）**
  - **Given** 模擬舊 `input/courses`、未對齊校名資料夾、單數分類、note-studio 舊筆記與 `deleted/`
  - **When** 執行 `plan_consolidation`（dry-run）與 `apply_consolidation`
  - **Then** dry-run 不改任何檔案與 DB；apply 後路徑前綴同步且同名檔不覆寫，`deleted/` 僅盤點不刪不搬
  - 對應測試：`tests/test_legacy_consolidation.py`

## 6. 未決問題（Task 16 動真實資料前須逐題請使用者確認）

| # | 問題 | 目前採行預設 |
|---|---|---|
| Q1 | `DATA_DIR/deleted/`（344 MB）保留政策 | 永久保留；僅提供盤點與經使用者 `confirm=True` 才執行的手動清理，不自動刪除 |
| Q2 | `02 Handouts` 的 `.pptx`／`.docx` 處理方式 | 只列入學習紀錄與檔案清單，不自動轉檔、不上傳為講次來源 |
| Q3 | 文獻 PDF 預設歸檔位置 | `01 Materials/Literature_Review`（透過 `CategoryRole.MATERIALS` 解析，不寫死字串） |
| Q4 | `01 Materials`（課本）是否上傳為 NotebookLM 來源 | 預設不上傳；由課程設定勾選「課本作為整門課來源」（`materials_as_source`）控制 |
| Q5 | 現有真實資料課程對照 | `115-1`（生涯諮商）→ `115-1_CP31000`（`CP__31000-生涯諮商與實務`）；`心理學研究法` → `CP__30210`；確認 `midterm-submission/` 歸屬與 `deleted/115-1-20261112-182701` 是否還原 |

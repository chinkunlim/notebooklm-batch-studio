# ADR-014：課程身分（學期＋課號）與學習資料庫目錄結構

- **狀態**：Accepted
- **日期**：2026-11-24
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 背景與問題

實務盤點發現 `ADR-011` 導入統一學習目錄後仍存在三項結構性問題：
1. **課程代碼三規則不一致**：舊解析函式 `parse_course_folder_name("CP__30000-團體諮商")` 回傳 `('CP', '30000-團體諮商')`，導致同系所不同課程（如 `CP__30000`、`CP__31000`）代碼全部碰撞成 `CP` 而互相覆蓋；同一課號跨學期重修也無法並存。
2. **舊佈局與硬編碼殘留**：`input/courses/`、`output/courses/`、`output/imported_sources/` 與 `study/` 三套佈局並存，檔案監看、資料夾挑選、上傳來源與閃卡搜尋仍會碰觸舊佈局或跨課 glob（`ISSUE-058`～`ISSUE-065`）；且分類硬編碼為單數 `01 Material`／`02 Handout`，與使用者實際複數習慣及課本／講義區隔衝突。
3. **缺少舊學期管理與封存生命週期**：匯入過去學期課程（113-1 起）只為了建立完整學習紀錄，不應排程消耗 Gemini Notebook 額度，也不應因刪除課程而失去測驗與錯題紀錄。

## 2. 評估過的方案

| 方案 | 課程代碼規則 | 優點 | 缺點 |
|---|---|---|---|
| **A：學期＋課號（`<學期>_<課號>`，採用）** | 例如 `115-1_CP30000`；非標準資料夾手動指定課號後同樣組合 | 人類與 URL/檔名皆可讀、天然區隔跨學期重修與同系所不同課號、直接通過 `validate_path_segment`、支援安全改碼遷移 | 資料夾未依校方命名時（如 `專題`）需手動填寫課號；既有錯誤代碼需提供交易式 `rename_code` 遷移 |
| **B：自由自訂代碼** | 例如 `GROUP_COUNSEL`、`PSY201` | 彈性高、舊資料不用改碼 | 容易因命名不一致在重修或同系所撞名，且與資料夾名稱脫鉤、掃描難以自動對應 |
| **C：隨機 UUID 作主鍵** | 例如 `c9a3f1e2-...` | 絕對不撞名、改課名免改鍵 | URL、本機暫存檔名（`scratch/notes/<code>`）、MCP 參數對使用者與 AI 皆極不友善 |

## 3. 決策與理由

採 **方案 A（`<學期>_<課號>`）**，並一併確立以下學習資料庫與生命週期規範：

1. **課程代碼與資料夾解析（`domain/course_identity.py`）**：
   - 校方課程資料夾格式 `^([A-Za-z]{1,6})_{1,2}([0-9A-Za-z]+)-(.+)$`，將系所與課號相接轉大寫為 `course_no`（`CP__30000` → `CP30000`、`YY__5061AA` → `YY5061AA`），完整保留課名（含空白、括號、全形字、底線）。
   - 代碼為 `<term>_<course_no>`，並經 `domain/path_safety.validate_path_segment` 驗證；遠端筆記本標題規則為 `[<course_no>] <name> (<term>)`。
2. **分類預設複數、角色與別名（`domain/study_layout.py`）**：
   - 五大角色（`CategoryRole`）：`MATERIALS`（預設 `01 Materials`）、`HANDOUTS`（`02 Handouts`）、`NOTES`（`03 Notes`）、`HOMEWORK`（`04 Homework`）、`ASSIGNMENTS`（`05 Assignments`），可透過 `.env` 的 `STUDY_CATEGORIES`（5 個逗號分隔）覆寫。
   - `01 Material` 與 `02 Handout` 設為讀取別名：掃描與讀取合併兩者內容，建立目錄時若別名已存在則不重複建複數資料夾。
   - **講次邊界**：只有 `02 Handouts`（含子資料夾）的 `.pdf` 成為講次；`01 Materials` 是課本與文獻，預設不上傳，僅在課程勾選 `materials_as_source` 時才作為整門課來源；`02 Handouts` 中的 `.pptx`／`.docx` 只列入學習紀錄。
   - `03 Notes` 內除專案管理的 `NotebookLM/`、`NoteStudio/`、`QA_Notes/` 外，其餘使用者個人隨筆一律不可移動或覆寫。
3. **統一路徑與 `scratch/<種類>`（`config/settings.py`）**：
   - 徹底退場 `input/courses/`、`output/courses/`、`output/imported_sources/`：上傳的自訂來源存 `<HANDOUTS>/_uploaded/`（無 `study_dir` 時存 `scratch/uploads/<code>/`）。
   - 所有未歸檔或撤銷歸檔檔案統一放在 `DATA_DIR/scratch/<kind>/`，種類限定五種：`literature`、`notes`、`outputs`、`uploads`、`unarchived`。
   - 集中所有 `DATA_DIR` 子路徑於 `AppConfig`，移除 `entrypoints/` 與 `config/` 以外的隱式 `load_config()`。
4. **課程生命週期與舊學期 `record-only`：active → archived → 刪除（只移除資料庫）**：
   - 新增 `CourseStatus`（`active` / `archived`）與 `ProfileName.RECORD_ONLY`。
   - 課程生命週期採 Google Classroom 模式：平常只做「封存」，**只有 `status == archived` 的課程才能刪除**；未封存一律拒絕刪除（HTTP 409、MCP `confirm_warning`、UI 刪除鈕停用）。
   - 舊學期課程掃描登錄後設為 `record-only` + `archived`，絕不排入生成佇列，亦排除於佇列認領、Today 與到期複習、預設課程選單之外，但仍完整納入學習紀錄彙整。
   - 刪除課程只移除本程式資料庫紀錄（並回報 8 張學習紀錄表的 `learning_records_removed` 筆數），**`study/` 內任何檔案（含 `03 Notes/NotebookLM`、`QA_Notes`、`NoteStudio` 與個人隨筆）一律不動不搬**，僅將舊佈局 `output/courses/<code>` 與 `needs_review/<code>_*` 移入 `deleted/`。

## 4. 影響與代價

- `ADR-011` 部分條文（單數分類 `01 Material`、`02 Handout`、掃描 `01 Material` 為講次來源、以 `<學年>-<學期>/<科目>` 當作唯一課程身分）由本 ADR 修訂。
- 資料庫需新增 `courses.status` 與 `courses.course_no` 欄位，並將 `literature_items.target_category` 預設值改為 `"01 Materials"`（不修改既有列，讀取以角色相容）。
- 現有本機資料（如 `115-1/生涯諮商`、舊 `input/courses/`、單數分類與 `note-studio` 109 份舊筆記）需透過 Task 15/16 的 dry-run-first 整併工具一次性對齊。

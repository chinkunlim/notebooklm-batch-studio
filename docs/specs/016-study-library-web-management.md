# SPEC-016：學習資料夾網頁管理（登錄舊課、手動登錄、scratch 歸檔、修改課程名稱）

- **狀態**：Implemented <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-25
- **相關任務 / ADR**：TASK-039、TASK-038 (1)、SPEC-014、核心規則 13

## 1. 目標

SPEC-014 的「掃描學習資料夾、批次登錄舊課、非標準資料夾手動登錄、scratch 歸檔／撤銷歸檔」只有 HTTP 與 MCP 入口，網頁沒有按鈕；課程顯示名稱也沒有任何入口可修改（2026-11-25 只能直接改資料庫）。本規格補齊網頁入口，並新增「修改課程顯示名稱」的三入口，讓使用者不需要 Agent 也能完成這些操作。

## 2. 使用情境

- **情境 A**：使用者把 113-1～114-2 的課程資料夾複製到 `study/<學期>/`，打開「學習紀錄」，看到標示「未登錄」的課程卡片，按「登錄」（預設同時封存），課程以 record-only 登錄，佇列不新增任何工作。
- **情境 B**：學期資料夾內有不符合 `CODE__NUM-課名` 的資料夾（例如 `專題`），在「其他資料夾」旁按「手動登錄…」，輸入課號後登錄。
- **情境 C**：`scratch/` 有尚未歸檔的檔案，在「學習紀錄」的「未歸檔檔案」卡片選擇課程與分類後按「歸檔」；課程分類檔案旁可按「撤銷歸檔」退回 `scratch/unarchived/<課程代碼>/`。
- **情境 D**：使用者在課程「進階工具」選「修改課程名稱…」，輸入新名稱；網頁、學習紀錄與 API 立即顯示新名稱，資料夾與課程代碼不變。

## 3. 需求

- **必須 (Must)**：
  1. 學習紀錄的「未登錄」課程卡片提供「登錄」按鈕與「同時封存」選項（預設勾選），呼叫 `POST /api/study/library/register`。
  2. 每個學期區塊提供「登錄本學期所有未登錄課程」按鈕，先確認數量再送出。
  3. 學期「其他資料夾／檔案」每一項提供「手動登錄…」，詢問課號後呼叫 `POST /api/study/library/register-folder`；錯誤訊息顯示在提示中。
  4. 學習紀錄頁新增「未歸檔檔案」卡片：列出 `GET /api/study/unfiled` 的項目，每項可選課程與分類（五個角色）後呼叫 `POST /api/study/file`。
  5. 已登錄課程的分類檔案清單每一項提供「撤銷歸檔」，確認後呼叫 `POST /api/study/unfile`；為此 `CourseRecordView` 新增 `study_dir` 欄位（預設空字串）。
  6. 修改課程顯示名稱：服務 `CourseRenameDisplayService`（或課程設定服務的方法）`set_display_name(code, name)`，只更新 `courses.name`（去除前後空白、不可空白、最長 255 字），不動 `code`、`subject`、資料夾與遠端筆記本；HTTP `PUT /api/courses/{code}/name {name}`；MCP `set_course_display_name(code, name, confirm=False)`；網頁「進階工具 → 修改課程名稱…」。
  7. 所有會改資料的網頁操作都先確認；MCP 工具 `confirm=False` 時只回傳警告。
- **可選 (Nice to have)**：登錄後自動重新整理課程清單與學習紀錄。
- **不做 (Out of scope)**：修改課程代碼（已由 SPEC-014 `rename_course_code` 提供）；同步修改 Gemini Notebook 遠端筆記本標題。

## 4. 介面 / API

- `PUT /api/courses/{code}/name`，body `{"name": "生涯諮商與實務"}` → `200 {"code": "...", "name": "..."}`；未知課程 `404`；空白名稱 `422`。
- MCP `set_course_display_name(code: str, name: str, confirm: bool = False) -> str`。
- 既有：`GET /api/study/library`、`POST /api/study/library/register`、`POST /api/study/library/register-folder`、`GET /api/study/unfiled`、`POST /api/study/file`、`POST /api/study/unfile`。

## 5. 驗收標準

- [x] **場景 16a**：Given `study/113-1/CP__30000-團體諮商/` 未登錄，When 網頁按「登錄」，Then 課程以 record-only＋archived 登錄、`artifact_jobs` 為 0。（`tests/test_study_library_web.py::test_web_ui_wires_register_and_register_folder`、`test_register_from_record_view_creates_record_only_course`）
- [x] **場景 16b**：Given 學期內有非標準資料夾，When 手動登錄並輸入課號，Then 以該課號登錄。（同上）
- [x] **場景 16c**：Given `scratch/uploads/a.pdf`，When 歸檔到某課程 `materials`，Then 檔案移到該課程 `01 Materials/`；When 撤銷歸檔，Then 移到 `scratch/unarchived/<code>/`；學習紀錄回傳 `study_dir`。（`test_record_view_exposes_study_dir_and_web_wires_filing`）
- [x] **場景 16d**：Given 課程名稱「生涯諮商」，When `PUT /api/courses/{code}/name` 為「生涯諮商與實務」，Then `GET /api/courses` 顯示新名稱，`subject`、`study_dir`、`code` 不變；空白名稱回 422；MCP `confirm=False` 不修改。（`test_set_display_name_http_mcp_and_web`）

## 6. 未決問題

- 無。

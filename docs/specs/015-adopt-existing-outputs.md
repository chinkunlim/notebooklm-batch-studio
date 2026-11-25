# SPEC-015：從既有產出檔建立產出紀錄（Adopt Existing Outputs）

- **狀態**：Approved <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-25
- **相關任務 / ADR**：SPEC-014 (Q6)

## 1. 目標

解決課程在整併或從 `deleted/` 複製還原後，磁碟 `03 Notes/NotebookLM/` 已保有完整產出檔，但資料庫 `artifact_jobs` 仍為 0 筆（導致學習紀錄「已完成產出」顯示為 0、學習狀態為 `not_started`、且一般重新登錄會重複排程浪費 Gemini Notebook 額度）的問題。

本功能讓使用者能安全掃描指定課程本機 `03 Notes/NotebookLM/`（及未指定 `study_dir` 時之 `output/courses/<code>/`）既有產出檔，重用既有命名規則將檔案反向納管（adopt）為 `status=done`、`version=1` 的 `artifact_jobs` 紀錄，**絕不呼叫 Gemini Notebook、不新建筆記本、不改變 `profile`、不更動磁碟任何檔案**。

## 2. 使用情境

- **情境 A**：使用者透過 `consolidate` 從 `deleted/` 複製還原《心理學研究法》6 講共 186 個 NotebookLM 產出檔到 `03 Notes/NotebookLM/`，並以 `record-only` 登錄課程 `115-1_CP30210`；接著先以 `dry_run=True` 預覽每個講次對應到的產出類型與未對應檔案，確認無誤後才執行寫入 `artifact_jobs`。
- **情境 B**：執行後，`115-1_CP30210` 在《學習紀錄》的「已完成產出」立即計入，學生可直接檢視讀書指南、開啟第 1 講測驗並提交作答寫入 `quiz_attempts`，同時既有 `record-only` 設定、檔案與工作佇列（`claim_next_job`）不受任何影響。

## 3. 需求

- **必須 (Must)**：
  1. 掃描課程輸出根目錄 `resolve_course_output_root(config.courses_output_dir, course.code, course.study_dir)`：
     - 子資料夾 `<NN>_<slug>/` 依開頭數字 `NN` 對應 `lecture_no = int(NN)`。
     - 子資料夾 `_course_synthesis/` 對應全課程（`lecture_no = None`）。
  2. 檔名到 `ArtifactType` 的對應**直接重用現有模組定義與命名常數**（不另行維護第二份對照表）：
     - `services/artifact_runner.py`：`SIMPLE_OUTPUTS`、`REPORT_FORMATS`、`MIND_MAP_TYPES`
     - `services/quiz_runner.py`：`QUIZ_TYPES`、`MOCK_EXAM_TYPES`
     - `services/converters/image_fitter.py`：`DEVICE_TARGETS`（辨識 `infographic_{A4,iPadAir4,MacBookPro14}.*` 附屬檔）
     - `domain/naming.py`：`label_for`
     - 語音、測驗伴隨檔（`*_quiz.json`、`*_interactive_quiz.html`、`*_題目卷.{md,pdf}`、`*_答案卷.{md,pdf}` 與相容副本 `quiz.json`／`答案卷.md`）、閃卡（`anki.csv` / `flashcards.json`）、心智圖（`mindmap.{opml,json,md}`）與報告（`*_briefing_doc.md` 等及其 `*_interactive.html`）；支援課程改碼前的檔名前綴（如 `115-1_L01_audio.m4a`）。
  3. 未能對應到任何產出類型的檔案列為 `unmapped_files` 回報，不建立紀錄。
  4. 每個對應到的 `(lecture_no, artifact_type)` 建立一筆 `ArtifactJob`：`status=JobStatus.DONE`、`version=1`、`output_file`／`interactive_path` 指向既有檔案路徑、`source_origin="adopted"`。
  5. 若資料庫已存在相同 `(course_code, lecture_no, artifact_type)` 工作則跳過（`skip`），不覆寫、不重複建立。
  6. 預設 `dry_run=True`；`dry_run=True` 時資料庫與檔案系統零異動。
  7. 全程不建立 `NotebookLMAdapter`、不發送任何網路呼叫、不修改 `course.profile` 與 `course.status`、不搬移或修改任何磁碟檔案。
- **可選 (Nice to have)**：
  - 無（聚焦於本機納管）。
- **不做 (Out of scope)**：
  - 不連線 Gemini Notebook 反查 `notebook_id` 或遠端 `artifact_id`。
  - 不修改或搬移任何未對應檔案、不刪除或覆寫既有的 `artifact_jobs`。

## 4. 介面 / API

### 4.1 Service
- `AdoptOutputsService(config, course_repo, queue_repo).adopt_existing_outputs(code, dry_run=True) -> dict[str, Any]`
  - 位置：`src/notebooklm_batch_studio/services/adopt_outputs.py`
  - 若課程不存在，拋出 `CourseNotFoundError`。

### 4.2 HTTP
- `POST /api/courses/{code}/adopt-outputs`
  - Request Body：`{"dry_run": true}`（預設 `true`）
  - Response（`200 OK`）：
    ```json
    {
      "course_code": "115-1_CP30210",
      "dry_run": true,
      "output_root": ".../03 Notes/NotebookLM",
      "lectures": [
        {
          "lecture_no": 1,
          "folder": "01_Introduction-to-Scientific-Research",
          "matched": [
            {
              "artifact_type": "quiz_1",
              "label": "測驗 1・基礎",
              "output_file": ".../quiz_1_quiz.json",
              "interactive_path": ".../quiz_1_interactive_quiz.html",
              "status": "create"
            }
          ],
          "unmapped_files": []
        }
      ],
      "unmapped_files": [],
      "would_create": 8,
      "would_skip": 0,
      "created": 0,
      "skipped": 0
    }
    ```
  - 錯誤：`404`（找不到課程）。

### 4.3 MCP
- `adopt_existing_outputs(code: str, dry_run: bool = True, confirm: bool = False) -> str`
  - 位置：`src/notebooklm_batch_studio/entrypoints/mcp_study_library.py`
  - `confirm=False` 一律回傳 `confirm_warning(...)`（`{"confirmed": false, ...}`）。

### 4.4 Web UI
- 位置：課程進階工具選單（`studio-batch.js` / `studio-record.js`）。
- 按鈕「從既有檔案建立產出紀錄」點擊後先呼叫 `POST /api/courses/{code}/adopt-outputs`（`dry_run: true`）顯示各講對應數量與未對應檔案摘要，確認後再送出 `dry_run: false`。

## 5. 驗收標準（Given / When / Then）

- [ ] **場景 15a（資料夾與檔名規則對應及未對應清單）**
  - **Given** 課程於 `03 Notes/NotebookLM/01_Introduction-to-Scientific-Research/` 放有真實 31 個產出檔（含 `115-1_L01_audio.m4a`、3 組測驗、閃卡、心智圖、資訊圖表與裝置版、讀書指南）加上不明檔案 `stray_notes.txt`，且 `_course_synthesis/` 含全課程報告、模擬考與心智圖
  - **When** 呼叫 `adopt_existing_outputs(..., code, dry_run=True)`
  - **Then** 正確對應講次 1（8 項產出類型）與全課程（3 項產出類型）、`stray_notes.txt` 列入 `unmapped_files` 不建立工作、`dry_run=True` 下資料庫 `artifact_jobs` 仍為 0
  - 對應測試：`tests/test_adopt_outputs.py::AdoptOutputsTests::test_dry_run_maps_real_filenames_course_synthesis_and_reports_unmapped`

- [ ] **場景 15b（`dry_run=False` 寫入、冪等跳過、不改檔與不連網）**
  - **Given** `record-only` 課程第 1 講已有 1 筆手動建立的 `study_guide` 工作（`done`），磁碟含全套既有檔案
  - **When** 呼叫 `adopt_existing_outputs(..., code, dry_run=False)`
  - **Then** 其餘類型寫入 `status="done"`、`version=1`、`output_file`／`interactive_path` 指向既有檔案；已存在的 `study_guide` 跳過不覆寫；未呼叫 NotebookLM；`course.profile` 仍為 `record-only` 且檔案未異動；重跑第二次全部跳過（`created == 0`）
  - 對應測試：`tests/test_adopt_outputs.py::AdoptOutputsTests::test_apply_creates_done_jobs_skips_existing_and_preserves_record_only_and_files`

- [ ] **場景 15c（學習紀錄計入、測驗可讀寫 `quiz_attempts`、佇列不重跑）**
  - **Given** `record-only` 課程已完成 `adopt_existing_outputs(..., dry_run=False)`
  - **When** 呼叫 `LearningRecordService.build()`、`GET /api/courses/{code}/lectures/1/quiz/quiz_1`、`POST /api/courses/{code}/study/quiz-attempts` 與 `QueueRepository.claim_next_job()`
  - **Then** 學習紀錄 `stats["artifacts_done"]` 計入已建工作數、測驗端點回 `200`、交卷回 `200` 並寫入 `quiz_attempts`、`claim_next_job()` 回傳 `None`
  - 對應測試：`tests/test_adopt_outputs.py::AdoptOutputsTests::test_adopted_outputs_update_learning_record_enable_quiz_attempts_and_stay_out_of_queue`

- [ ] **場景 15d（HTTP、MCP `confirm` 防護與 Web UI 三入口）**
  - **Given** 測試客戶端與全工具註冊器已掛載
  - **When** 呼叫 HTTP `POST /api/courses/{code}/adopt-outputs`（含未知課程 404 與 `dry_run` true/false）、MCP `adopt_existing_outputs`（`confirm=False` 拒答與 `confirm=True` 執行）及檢查前端靜態程式碼
  - **Then** HTTP 與 MCP 行為正確、`confirm=False` 回傳 `{"confirmed": false, ...}`、前端包含先 dry-run 預覽再確認的「從既有檔案建立產出紀錄」流程
  - 對應測試：`tests/test_adopt_outputs.py::AdoptOutputsTests::test_http_mcp_and_web_ui_adopt_outputs_entrypoints`

## 6. 未決問題 / 後續待辦

- **多版本產出反查**：若日後支援多版本檔案 `*_v2.*` 反查，可於後續版本擴充。
- **NoteStudio 非章節檔案瀏覽（建議 ②）**：`list_chapter_notes`／`find_chapter_note` 已涵蓋頂層與 `學習筆記/原稿/` 之縫合章節；針對 `00_總覽與跨章整合筆記.md`、`學習筆記/PDF/*.pdf` 與 `章節/**/目前/*.md` 等非縫合檔案，日後可補 `list_note_files`／`read_note_file` 依相對路徑瀏覽，不混入章節清單。

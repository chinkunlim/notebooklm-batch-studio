# SPEC-013：note-studio 模組化學習筆記（每章 Markdown 原稿、推回來源、舊筆記匯入）

- **狀態**：Implemented <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-24（依 TASK-026、TASK-027 已上線的行為補寫）
- **相關任務 / ADR**：TASK-026、TASK-027、TASK-028 / ADR-011、ADR-012、ADR-013

## 1. 目標

把原本獨立的 `note-studio` 併進本專案：每一章講義用 7 個模組提示詞（心智圖、詳細大綱、QEC、康乃爾、比較矩陣、費曼、複習題）生成 Markdown，驗證、清洗後縫合成一份單章 `.md` 原稿。原稿保留 `[核心]`、`{{定義:...}}`、`:::QEC` 等語意標記，留給之後的 PDF 排版（階段三）使用。

成功的樣子：在研讀工作室選好課程和章節後按「生成」，`<study_dir>/03 Notes/NoteStudio/` 就會出現 `ch01_<標題>_學習筆記.md`；可以重跑單一模組，舊版本自動封存；也可以把筆記轉成 PDF 推回 Gemini Notebook 當來源。

## 2. 使用情境

- **學生**：在網頁「筆記」面板選課程與講次（自動帶入課名、章節標題、講義 PDF），預覽或複製提示詞，按生成；中途可暫停。
- **Agent**（Claude Code、Open WebUI 等）：透過 MCP `notes_*` 工具列出／預覽提示詞、生成章節（需 `confirm=True`）、讀取原稿、推回來源、匯入舊筆記。
- **使用者手動調整提示詞**：在 `DATA_DIR/prompts/modular_specs/` 放同名 `.md` 檔，就會覆蓋內建的 `assets/prompts/modular_specs/`，不必改程式碼。

## 3. 需求

- **必須 (Must)**：
  - 7 個標準步驟（`01_mindmap` … `07_quiz`），每步檢查必要標記（例如 `:::QEC`、表格 `|`），`05_matrix` 失敗時只記警告、不中斷（soft fail）。
  - 雙後端：`gemini_web`（Playwright 操作 Gemini 網頁，主要）與 `notebooklm`（`ask_in_conversation`，只勾選該章 `source_ids`，備用）。
  - 偵測額度用完、模型被降級、制式拒答時停在 `quota_wait`，不無效重試；使用者可要求暫停（跨程序的 pause 檔）。
  - 重跑前把舊模組檔與縫合檔封存到 `versions/<chapter_id>/<UTC 時間戳>/`。
  - 輸出位置：課程有 `study_dir` 時寫到 `<study_dir>/03 Notes/NoteStudio/`，沒有時寫到 `DATA_DIR/scratch/notes/<course_key>/`；狀態存在 `DATA_DIR/state/notes/`。
  - **路徑安全（ISSUE-045、ADR-013）**：`course_key`、`chapter_id` 不可含 `/`、`\`、NUL、萬用字元，也不可以 `.` 開頭；`study_dir` 必須在 `DATA_DIR` 或 `STUDY_ROOT_DIR` 內；`pdf_path` 必須是 `.pdf`，而且在 `DATA_DIR`、`STUDY_ROOT_DIR` 或該課程登錄的 `source_dir` 內。
  - 三入口一致：HTTP（`/api/notes/*`）、MCP（`notes_*`）、網頁面板呼叫同一個 `NotePipelineService`。
- **可選 (Nice to have)**：`08_supplement_spec.md` 補充模組（目前不在標準 7 步內）。
- **不做 (Out of scope)**：PDF 向量排版（Node/Chrome/ELK 渲染器）留到階段三。

## 4. 介面 / API

| HTTP | MCP | 說明 |
|---|---|---|
| `GET /api/notes/prompts` | `notes_list_prompts` | 列出模組提示詞檔 |
| `POST /api/notes/prompts/preview` | `notes_preview_prompt` | 填入課名／章節後的完整提示詞 |
| `GET /api/notes/status/{course_key}` | `notes_get_status` | 各章狀態、已完成步驟、是否暫停 |
| `POST /api/notes/generate` | `notes_generate_chapter(params, confirm)` | 生成或重跑（`steps_override` 可只跑部分模組） |
| `POST /api/notes/pause/{course_key}`、`/resume/{course_key}` | `notes_pause_course(confirm)` | 要求在目前步驟結束後暫停／解除 |
| `GET /api/notes/content/{course_key}/{chapter_id}` | `notes_read_chapter` | 讀取縫合後的 `.md` |
| `GET /api/notes/chapters/{course_key}` | `notes_list_chapters` | 列出已縫合章節 |
| `POST /api/notes/push_to_source` | `notes_push_to_source(confirm)` | 轉 PDF 後上傳為 Gemini Notebook 來源 |
| `POST /api/notes/import_legacy` | `notes_import_legacy(confirm)` | 從舊 `note-studio` 資料夾複製 `.md`（預設不覆蓋） |

生成請求範例：

```json
{"course_key": "PSY201", "course_name": "心理學研究法", "chapter_id": "ch01",
 "chapter_title": "科學研究導論", "backend": "gemini_web", "model": "4 Argon",
 "pdf_path": "<STUDY_ROOT_DIR>/115-1/心理學研究法/02 Handout/01.pdf"}
```

回應：`{"status": "done" | "paused" | "quota_wait", "stitched_path": "...", "completed_steps": [...], "backend": "gemini_web"}`。識別碼或路徑不合法時 HTTP 回 400、MCP 回錯誤訊息，磁碟上不會留下任何檔案。

## 5. 驗收標準

- [x] 提示詞載入與 `DATA_DIR` 覆蓋（`tests/test_note_pipeline_phase1.py::test_standalone_prompt_loading_and_override`）
- [x] 清洗與驗證保留語意標記、擋下制式拒答（`test_normalizer_and_validator_preserve_semantic_tags`）
- [x] `gemini_web` 生成 7 模組並縫合、重跑時封存（`test_gemini_web_primary_generates_and_stitches_md_with_version_archive`）
- [x] `notebooklm` 後端只用該章 `source_ids`（`test_notebooklm_fallback_backend_uses_source_ids`）
- [x] 章節列表、推回來源、舊筆記匯入、HTTP/MCP 一致（`tests/test_note_pipeline_phase2.py`）
- [x] 路徑穿越與資料夾外 PDF 一律拒絕（`tests/test_security_hardening.py::NotePathTraversalTests`）

## 6. 未決問題

- 階段三 PDF 排版的渲染器選擇（沿用 note-studio 的 Node/Chrome，或改用本專案既有的 Python PDF 轉換）。
- `08_supplement` 是否納入標準步驟。

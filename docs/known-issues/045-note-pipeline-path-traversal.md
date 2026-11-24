# ISSUE-045：筆記管線可用 ../ 或任意路徑讀寫資料夾外檔案

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-028`

## 1. 現象

notes 的 HTTP 與 MCP 介面接受任意 course_key、chapter_id、study_dir、pdf_path、legacy source_dir；course_key='../../x' 會把筆記寫到 DATA_DIR 外，pdf_path 可把電腦上任何檔案上傳到 Gemini。

- **錯誤訊息**：無（請求成功，檔案寫到資料夾外，沒有錯誤）
- **重現步驟**：`POST /api/notes/generate` 帶 `{"course_key": "../../escape", "chapter_id": "ch01"}`，或 MCP `notes_generate_chapter` 帶 `pdf_path="/任意/檔案.pdf"`。
- **影響範圍**：所有能呼叫 127.0.0.1:8768 或 MCP 的程式／Agent；可寫入 DATA_DIR 外、把本機任意 PDF 上傳到 Gemini。

## 2. 根本原因

note-studio 整合時只在 state_manager 清理 course_key，NotePipelineService 直接把識別碼與呼叫端路徑接成 Path，沒有驗證是否仍在允許的資料夾內。

## 3. 修正或規避方式

新增 domain/path_safety.py（validate_path_segment、ensure_within_roots）；services/notes/note_paths.py 的 NotePathResolver 在動到磁碟前驗證：識別碼不可含分隔符號、.. 開頭或萬用字元；study_dir 必須在 DATA_DIR / STUDY_ROOT_DIR；pdf_path 必須是 .pdf 且在 DATA_DIR / STUDY_ROOT_DIR / 該課程登錄的 source_dir。（相關程式碼註解加 `Refs: ISSUE-045`）

## 4. 防回歸

tests/test_security_hardening.py::NotePathTraversalTests（7 個案例，含 HTTP 400）。

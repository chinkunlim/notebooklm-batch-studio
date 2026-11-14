# SPEC-011: Gemini Notebook 探索提問、問答筆記庫與階層標籤系統 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為「Gemini Notebook 學習工作室」建立隨身問答抽屜、問答筆記庫大頁面、NotebookLM 格式化精華總結、四大維度階層標籤、測驗盲點追問收錄，以及單篇/多篇合併回灌至筆記本來源之完整閉環功能。

**Architecture:**
前端提供隨身右側滑出抽屜（`studio-qa-drawer.js`）與研讀工作台大頁面（`studio-notes-tab.js`）。後端透過 `QANotesService` 呼叫 `notebooklm-py` 的 `client.chat.ask` 進行多輪對話與模板總結；筆記同時持久化為本地標籤相容 Markdown（存入 `$DATA_DIR/output/courses/<course>/notes/`）與 SQLite `course_qa_notes` 資料庫記錄，並透過現有 `CourseSourceMixin` 支援單篇與合併打包上傳至 Gemini Notebook 來源。

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, notebooklm-py, pypdf/ReportLab, Vanilla ES6+ HTML5/CSS3.

**Spec:** [`docs/specs/011-notebook-qa-notes-and-tag-system.md`](../../specs/011-notebook-qa-notes-and-tag-system.md)

## Global Constraints

- 單一檔案長度上限 500 行（嚴格遵守 `.agents/project.toml` `max_file_lines = 500`）。
- 函式長度上限 40 行，參數上限 4 個，巢狀深度上限 3 層（`review_guard.py` 嚴格把關）。
- 註解規範：所有 Python 檔頭、類別、函式必須具備完整 docstring（含 `Args:` 與 `Returns:`）；JavaScript 頂層與內部宣告函式必須具備完整 JSDoc（含 `@param` 與 `@returns`）。
- 嚴禁修改使用者原始課程資料夾中的 PDF；所有筆記儲存於 `$DATA_DIR/output/courses/<course>/notes/`，上傳暫存於 `courses_input_dir/<course>/_uploaded_sources/`。
- MCP 寫入/刪除工具必須包含 `confirm: bool = False` 參數保護。
- 100% 離線測試驗證：所有單元測試與 API 測試一律使用 Mock 或 `DummyStudioClient`，不發送外部網路請求。

## Review Focus

1. **對話上下文隔離 (Conversation Drift)**：切換課程或點擊「開啟新話題」時，必須徹底清空前次 conversation_id，避免不同課程或不同章節的問答混淆。
2. **50 份來源上限保護 (Source Limit Overflow)**：單篇與多篇合併上傳至來源前，必須先呼叫 `_check_source_limit`，防止超出帳號來源上限。
3. **Markdown Frontmatter 完整性 (Frontmatter Mutation)**：切換掌握度（`needs_review` ⇄ `mastered`）或編輯備忘時，實體 `.md` 檔案的 YAML 前言與正文必須正確原子更新，不能破壞標籤格式或丟失內容。
4. **測驗追問去重 (Quiz Explain Dedup)**：同一題測驗多次點擊「收錄至問答筆記庫」時，應更新既有筆記而非無限重複堆疊垃圾檔案。
5. **Obsidian 階層標籤相容性 (Tag Formatting)**：標籤輸出格式必須符合 `#大/中/小` 巢狀語法（如 `#課程/BIO101/L03`、`#類型/測驗追問`、`#掌握度/待加強`、`#主題/領域/概念`）。

---

## Tasks

### Task 1: 資料庫模型與 Alembic 遷移 (Database Schema & Migration)

**Files:**
- Modify: `src/notebooklm_batch_studio/adapters/db/models.py`
- Modify: `src/notebooklm_batch_studio/domain/models.py`
- Migration: `alembic/versions/*_add_course_qa_notes.py`
- Test: `tests/test_qa_notes_db.py`

- [ ] **Step 1: Write failing DB model test**
  在 `tests/test_qa_notes_db.py` 中測試 `CourseQANoteRecord` 的 CRUD 操作，驗證 `tags_json` 欄位序列化、FK 關聯 `courses.code` 與掌握度狀態預設值為 `needs_review`。
- [ ] **Step 2: Run test to confirm failure**
  執行 `uv run python -m unittest tests/test_qa_notes_db.py` 確認因尚未定義 Model 而失敗。
- [ ] **Step 3: Implement domain & DB models**
  - 在 `domain/models.py` 中定義 `CourseQANote` 資料類別與 `MasteryStatus` 列舉。
  - 在 `adapters/db/models.py` 中定義 `CourseQANoteRecord` 表結構（`id`, `course_code`, `lecture_no`, `title`, `content_markdown`, `personal_memo`, `tags_json`, `source_scene`, `mastery_status`, `is_uploaded_as_source`, `uploaded_source_id`, `created_at`, `updated_at`）。
- [ ] **Step 4: Generate and apply Alembic migration**
  執行 `uv run alembic revision --autogenerate -m "add course_qa_notes table"` 並執行 `uv run alembic upgrade head`。
- [ ] **Step 5: Verify test passes**
  執行 `uv run python -m unittest tests/test_qa_notes_db.py` 驗證綠燈。
- [ ] **Step 6: Commit Task 1**
  執行 `python3 scripts/agentctl.py commit --agent antigravity --model claude-opus-4-6 -m "feat(db): add course_qa_notes model and alembic migration (SPEC-011)"`

---

### Task 2: DummyStudioClient 與 Adapter 對話能力擴充 (Chat & Q&A Protocol)

**Files:**
- Modify: `src/notebooklm_batch_studio/domain/notebooklm_protocol.py`
- Modify: `src/notebooklm_batch_studio/adapters/notebooklm/client.py`
- Modify: `tests/dummy_client.py`
- Test: `tests/test_notebooklm_adapter.py`

- [ ] **Step 1: Write failing adapter chat tests**
  在 `tests/test_notebooklm_adapter.py` 增加 `test_ask_question_returns_answer_and_citations` 測試，驗證 `ask_question(notebook_id, question, source_ids=None, conversation_id=None)` 回傳字典結構。
- [ ] **Step 2: Run test to confirm failure**
  確認 `NotebookLMAdapter` 尚無 `ask_question` 方法。
- [ ] **Step 3: Update protocol & adapter implementation**
  - 在 `domain/notebooklm_protocol.py` 定義 `ask_question(notebook_id: str, question: str, source_ids: list[str] | None = None, conversation_id: str | None = None) -> dict[str, Any]`。
  - 在 `adapters/notebooklm/client.py` 實作 `@_translate_errors async def ask_question`，調用 `client.chat.ask` 並標準化回傳。
  - 在 `tests/dummy_client.py` 擴充 `DummyStudioClient.ask_question` 支援模擬對話、追蹤 `conversation_id` 與引用來源。
- [ ] **Step 4: Verify adapter test passes**
  執行 `uv run python -m unittest tests/test_notebooklm_adapter.py` 確認通過。
- [ ] **Step 5: Commit Task 2**
  執行 `python3 scripts/agentctl.py commit --agent antigravity --model claude-opus-4-6 -m "feat(adapter): add chat ask_question protocol and dummy client support (SPEC-011)"`

---

### Task 3: QANotesService 核心服務與 Markdown 標籤持久化 (Service Layer)

**Files:**
- Create: `src/notebooklm_batch_studio/services/qa_notes_service.py`
- Modify: `src/notebooklm_batch_studio/services/orchestrator.py`
- Test: `tests/test_qa_notes_service.py`

- [ ] **Step 1: Write failing service tests**
  在 `tests/test_qa_notes_service.py` 中測試：
  - `ask(course_code, question, lecture_no=None, conversation_id=None)`
  - `summarize_and_format(course_code, conversation_id, lecture_no=None)` 格式化模板注入與解析
  - `save_note(course_code, ...)` 本地 Markdown 寫入（含 YAML Frontmatter 與四大維度標籤）及 DB 儲存
  - `toggle_mastery(note_id, status)` 更新 DB 與實體 `.md` 檔案標籤
  - `push_note_to_source(course_code, note_id)` 單篇回灌
  - `bundle_notes_to_source(course_code, note_ids, title)` 多篇合併為單一 PDF/來源回灌
- [ ] **Step 2: Run test to confirm failure**
  確認 `QANotesService` 模組尚不存在。
- [ ] **Step 3: Implement QANotesService**
  - 建立 `src/notebooklm_batch_studio/services/qa_notes_service.py`（控制在 400 行以內）：
    - 實作對話管理、Prompt 模板總結、階層標籤解析。
    - 實作本地 Markdown 序列化與原子寫入（`courses_output_dir/<course>/notes/`）。
    - 實作單篇回灌與多篇合併打包（呼叫 ReportLab 產生精美合併 PDF 並呼叫 `source_manager` 上傳）。
  - 在 `orchestrator.py` 整合 `qa_notes_service` 屬性。
- [ ] **Step 4: Verify service tests pass**
  執行 `uv run python -m unittest tests/test_qa_notes_service.py` 確認全部綠燈。
- [ ] **Step 5: Commit Task 3**
  執行 `python3 scripts/agentctl.py commit --agent antigravity --model claude-opus-4-6 -m "feat(services): implement QANotesService with hierarchical tags and source bundling (SPEC-011)"`

---

### Task 4: HTTP 路由與 MCP 工具入口 (API & MCP Parity)

**Files:**
- Create: `src/notebooklm_batch_studio/entrypoints/http/qa_notes.py`
- Modify: `src/notebooklm_batch_studio/entrypoints/schemas.py`
- Modify: `src/notebooklm_batch_studio/entrypoints/api.py`
- Modify: `src/notebooklm_batch_studio/entrypoints/mcp_server.py`
- Modify: `src/notebooklm_batch_studio/entrypoints/mcp_course_settings.py`
- Test: `tests/test_qa_notes_api.py`

- [ ] **Step 1: Write failing API & MCP tests**
  在 `tests/test_qa_notes_api.py` 測試：
  - `POST /api/courses/{code}/qa/ask`
  - `POST /api/courses/{code}/qa/summarize`
  - `GET /api/courses/{code}/notes` (支援 tag / lecture_no 篩選)
  - `POST /api/courses/{code}/notes`
  - `PATCH /api/courses/{code}/notes/{id}/mastery`
  - `POST /api/courses/{code}/notes/{id}/push_to_source`
  - `POST /api/courses/{code}/notes/bundle_to_source`
  - MCP 工具 `ask_notebook_question`、`save_qa_note`、`list_course_notes`、`push_note_to_source`（含 confirm 防護）。
- [ ] **Step 2: Run test to confirm failure**
  確認路由尚未註冊。
- [ ] **Step 3: Implement schemas, HTTP router & MCP tools**
  - 在 `schemas.py` 新增 Pydantic 模型（`AskQuestionRequest`, `SummarizeRequest`, `SaveNoteRequest`, `MasteryUpdateRequest`, `BundleNotesRequest`）。
  - 在 `entrypoints/http/qa_notes.py` 實作乾淨路由處理。
  - 在 `entrypoints/api.py` 註冊 `qa_notes_router`。
  - 在 `entrypoints/mcp_course_settings.py` 註冊 MCP Q&A 工具群。
- [ ] **Step 4: Verify API & MCP tests pass**
  執行 `uv run python -m unittest tests/test_qa_notes_api.py` 確認通過。
- [ ] **Step 5: Commit Task 4**
  執行 `python3 scripts/agentctl.py commit --agent antigravity --model claude-opus-4-6 -m "feat(api,mcp): register QA and notes HTTP routes and MCP tools (SPEC-011)"`

---

### Task 5: 隨身提問抽屜與測驗追問聯動 (UI: Drawer & Quiz Integration)

**Files:**
- Create: `src/notebooklm_batch_studio/entrypoints/static/studio-qa-drawer.js`
- Modify: `src/notebooklm_batch_studio/entrypoints/static/index.html`
- Modify: `src/notebooklm_batch_studio/entrypoints/static/studio.js`
- Modify: `src/notebooklm_batch_studio/entrypoints/static/studio-study-panels.js`

- [ ] **Step 1: Add Drawer markup & styles to index.html**
  - 在 `index.html` 增加 `#qaDrawer`（包含收合拉柄、課程/講次切換、新話題按鈕、對話日誌區、一鍵總結按鈕與輸入框）。
  - 綁定全局快捷鍵 `⌘J` 開關抽屜。
- [ ] **Step 2: Implement studio-qa-drawer.js**
  - 撰寫 `openQaDrawer(lectureNo=null)`、`closeQaDrawer()`、`sendDrawerQuestion()`、`summarizeDrawerChat()`、`saveDrawerNote()`。
  - 支援單則隨手存與整串總結。
  - 引用頁碼點擊自動觸發 `openReaderToPage(pageNum)`。
- [ ] **Step 3: Connect Quiz explain to QA Notes**
  - 在 `studio.js` 的 `explainQuestion` 與 `studio-study-panels.js` 的 `explainMistake` 解析區塊，增加「📥 收錄為問答筆記」按鈕。
  - 點擊後直接呼叫 API 存檔並自動標記 `#類型/測驗追問` 與 `#掌握度/待加強`。
- [ ] **Step 4: Verify test_button_routes.py passes**
  執行 `uv run python -m unittest tests/test_button_routes.py` 確保新增的 fetch API 均符合 OpenAPI 宣告。
- [ ] **Step 5: Commit Task 5**
  執行 `python3 scripts/agentctl.py commit --agent antigravity --model claude-opus-4-6 -m "feat(ui): add floating QA drawer and quiz mistake collector (SPEC-011)"`

---

### Task 6: 問答筆記庫大頁面與標籤雲過濾 (UI: Full Notes Tab & Tag Filter)

**Files:**
- Create: `src/notebooklm_batch_studio/entrypoints/static/studio-notes-tab.js`
- Modify: `src/notebooklm_batch_studio/entrypoints/static/index.html`
- Modify: `src/notebooklm_batch_studio/entrypoints/static/studio-nav.js`
- Modify: `scripts/demo/demo-mock.js`
- Rebuild: `docs/demo/index.html`

- [ ] **Step 1: Add Notes Tab container to index.html & studio-nav.js**
  - 研讀工作台頂部分頁選單新增「問答筆記」（tab: `notes`）。
  - 容器具備雙欄佈局：左側標籤雲、搜尋框與筆記清單；右側筆記詳情預覽、個人備忘編輯區與操作列（掌握度切換、單篇回灌、多篇打包）。
- [ ] **Step 2: Implement studio-notes-tab.js**
  - 撰寫 `loadCourseNotes(code)`、`filterNotesByTag(tag)`、`toggleNoteMastery(noteId)`、`pushNoteToSource(noteId)`、`bundleNotesToSource()`。
  - 標籤支援四大維度階層點選與關鍵字快速搜尋。
- [ ] **Step 3: Update demo-mock.js and rebuild demo**
  - 在 `scripts/demo/demo-mock.js` 加入 `/api/courses/{code}/qa/*` 與 `/api/courses/{code}/notes/*` mock 路由。
  - 執行 `uv run python scripts/build_demo.py` 重新生成 `docs/demo/index.html`。
- [ ] **Step 4: Commit Task 6**
  執行 `python3 scripts/agentctl.py commit --agent antigravity --model claude-opus-4-6 -m "feat(ui): implement full QA notes studio tab and tag filter (SPEC-011)"`

---

### Task 7: 完整整合測試、代碼品質審查與收尾 (E2E Verification & Closeout)

**Files:**
- Modify: `tests/test_dummy_user_simulation.py`
- Test: Full unittest suite
- Audit: `scripts/agentctl.py check`

- [ ] **Step 1: Add E2E user simulation scenario**
  在 `tests/test_dummy_user_simulation.py` 中新增 `test_qa_notes_and_tag_lifecycle`，模擬使用者提問、精華總結、存為 Markdown、測驗追問收錄、掌握度切換至已搞懂，以及合併打包回灌為來源之完整生命週期。
- [ ] **Step 2: Run full test suite**
  執行 `uv run python -m unittest discover -s tests -v` 確保所有測試 100% 通過。
- [ ] **Step 3: Run agentctl check & code review guard**
  執行 `python3 scripts/agentctl.py check`，確保所有檔案符合 500 行上限、函式長度、完整 docstring、無未宣告 import，達成零警告零違規。
- [ ] **Step 4: Update PROJECT_TREE.md & Task Completion**
  - 執行 `python3 scripts/agentctl.py tree` 同步目錄樹。
  - 執行 `python3 scripts/agentctl.py task done TASK-024 --summary "Implemented SPEC-011 Gemini Notebook QA drawer, notes repo, hierarchical tags, quiz explain collector, and source bundling"`
- [ ] **Step 5: Final Commit**
  執行 `python3 scripts/agentctl.py commit --agent antigravity --model claude-opus-4-6 -m "feat(notes): complete SPEC-011 QA notes and hierarchical tag system"`

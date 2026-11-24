# 架構決策 (Architecture Decision Records)

記錄「為什麼這樣設計」：每個重要的架構取捨一個檔案，之後的人（或 Agent）不用再猜。

- 新增：`python3 .agents/skills/adr-issue-tracker/scripts/tracker_cli.py --add-adr <slug> --title "標題" --agent <名字>`
- 格式：[`_TEMPLATE.md`](_TEMPLATE.md)；在相關程式碼註解加 `Refs: ADR-NNN`。
- 決策被推翻時不要刪檔，把狀態改成 `Superseded by ADR-NNN`。

> 命名規則：`_TEMPLATE.md` 是新增紀錄時要照著寫的範本；紀錄檔命名為 `NNN-<slug>.md`。整個專案只有根目錄一份 `README.md`。

## 總表

| ADR | 標題 | 狀態 | 日期 | 相關程式 |
|---|---|---|---|---|
| [ADR-001](001-notebooklm-access.md) | 以 notebooklm-py 為主、Playwright 補位操作 NotebookLM | Accepted | 2026-10-21 | `src/notebooklm_batch_studio/adapters/notebooklm/` |
| [ADR-002](002-session-token-auth.md) | 以 session storage_state 驗證取代 .env 明文帳密 | Accepted | 2026-11-01 | `src/notebooklm_batch_studio/adapters/notebooklm/` |
| [ADR-003](003-student-study-portal-spaced-repetition.md) | 以 SQLite 與 Anki CSV 整合學生研讀工作台與間隔重複 | Accepted | 2026-11-01 | `src/notebooklm_batch_studio/adapters/db/study_repository.py, src/notebooklm_batch_studio/services/study_service.py` |
| [ADR-004](004-artifact-id-targeting.md) | 以 generate 回傳的 artifact_id 精準下載與改名，取代取最新一份 | Accepted | 2026-11-01 | `src/notebooklm_batch_studio/adapters/notebooklm/`, `src/notebooklm_batch_studio/services/artifact_runner.py` |
| [ADR-005](005-job-versions-and-generation-options.md) | 工作記錄 artifact id 與版本號，重新生成保留舊版；產出參數存於課程 | Accepted | 2026-11-01 | `src/notebooklm_batch_studio/services/course_settings.py`, `src/notebooklm_batch_studio/domain/naming.py`, `src/notebooklm_batch_studio/adapters/notebooklm/generation.py` |
| [ADR-006](006-gemini-notebook-display-name.md) | 產品改名 Gemini Notebook：只改顯示名稱，不改程式識別名稱 | Accepted | 2026-11-01 | — |
| [ADR-007](007-study-studio-visual-tiering-and-agency-architecture.md) | 研讀工作室認知視覺分級、奢華留聲形態與自主掌控架構 | Accepted（部分由 ADR-008 取代） | 2026-11-02 | `mockups_gallery.html`, `SPEC-009` |
| [ADR-008](008-v05-study-studio-shell.md) | 研讀工作室 v05 外殼：側欄導覽、設計與自訂移到側欄底部、靜態檔依職責拆分 | Accepted | 2026-11-02 | src/notebooklm_batch_studio/entrypoints/static/, docs/design/version_05_claude_template.html, SPEC-009 |
| [ADR-009](009-local-preferences-and-offline-fonts.md) | 網頁偏好記錄在本機資料庫；圖示與字型內建、可下載 Google Fonts | Accepted | 2026-11-02 | src/notebooklm_batch_studio/services/preferences_service.py, src/notebooklm_batch_studio/services/font_service.py, src/notebooklm_batch_studio/adapters/fonts/google_fonts.py, static/vendor/, tests/test_preferences.py, tests/test_fonts.py |
| [ADR-010](010-notebook-qa-notes-and-tag-system.md) | 以 NotebookLM 原生上下文整理問答精華筆記與階層標籤回灌閉環 | Accepted | 2026-11-14 | `src/notebooklm_batch_studio/services/qa_notes_service.py`, `src/notebooklm_batch_studio/services/qa_notes_formatter.py`, `src/notebooklm_batch_studio/adapters/db/notes_repository.py`, `src/notebooklm_batch_studio/entrypoints/http/qa_notes.py`, `src/notebooklm_batch_studio/entrypoints/mcp_qa_notes.py`, `src/notebooklm_batch_studio/entrypoints/static/studio-qa-drawer.js`, `src/notebooklm_batch_studio/entrypoints/static/studio-notes-tab.js`, `tests/test_qa_notes_service.py`, `tests/test_qa_notes_api.py` |
| [ADR-011](011-unified-study-hierarchy-and-literature-fetch.md) | 整合 literature-fetch 與統一學習目錄結構 (<學年>-<學期>/<科目>/<分類>) | Accepted | 2026-11-22 | TASK-025, SPEC-012, `domain/study_hierarchy.py`, `services/literature/`, `services/study_migration.py` |
| [ADR-012](012-note-studio-phase1-markdown-pipeline.md) | 整合 note-studio 階段一：雙後端模組化 Markdown 筆記生成與縫合管線 | Accepted | 2026-11-23 | TASK-026, TASK-027, SPEC-013, `services/notes/`, `entrypoints/mcp_notes.py` |
| [ADR-013](013-local-security-model.md) | 本機安全模型：提示注入防線、瀏覽器設定檔與圖書館帳密 | Accepted | 2026-11-24 | src/notebooklm_batch_studio/domain/path_safety.py, src/notebooklm_batch_studio/adapters/private_dir.py, src/notebooklm_batch_studio/entrypoints/http_middleware.py, src/notebooklm_batch_studio/config/settings.py |

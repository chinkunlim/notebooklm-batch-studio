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

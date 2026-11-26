# 🤝 Agent 狀態看板與交接紀錄 (`LATEST.md`)

> **AI Agent 開工必讀**：進入對話時請先閱讀下方「即時狀態看板」，確認上一位 Agent 的完成進度、待接手任務 (`handed_off`) 與注意事項；詳細過程請看本機的 `.agents/conversations/`。

<!-- LIVE_STATE_START -->
## 📊 即時狀態看板 (Live Snapshot)

- **最後更新時間**: `2026-11-26 01:02 UTC`
- **最近操作 Agent**: `claude-code`
- **目前 Git 分支**: `main`
- **最新 Git Commit**: `b538762 feat(study): suggest new course folders on 批次排程, create 01-05 when adding an in-study folder, and let watch follow textbook chapters in 01 Materials (SPEC-027) [agent:claude-code]`

### 🎯 進行中 / 待接手任務 (Active & Handed-Off Tasks)

| 任務 | 狀態 | 目前/上一位 Agent | 建議接手 | 相關範圍 | 已完成 | 待辦與卡點 |
|---|---|---|---|---|---|---|
| **TASK-036**<br/>User manual verification and housekeeping checklist | ⚪ `open` | `-` | `-` | - | - | **TODO**: 使用者實機確認與整理清單，見 .agents/tasks/TASK-036-checklist.md（逐項勾選並附證據）。 測試步驟與過時項目更正：docs/specs/026-pending-acceptance-and-manual-tests.md（#9 不要把測試 PDF 放進課本課程的 02 Handouts）。 |
| **TASK-040**<br/>Learning-site artifacts (per lecture and whole book) via Gemini Notebook chat and Studio download | 🟢 `in_progress` | `claude-code` | `-` | `docs/specs/021-learning-site-artifacts.md`, `docs/superpowers/plans/2026-11-25-learning-site-artifacts.md` | - | **TODO**: A 版（每講）已真實驗收並改名（ISSUE-071）。B 版（整本書）使用者 2026-11-25 決定先暫停：耗額度與 token，等使用者說要跑再跑；跑完即可結案。 B 版驗收步驟：docs/specs/026-pending-acceptance-and-manual-tests.md A1。 |
| **TASK-041**<br/>Link 115-1_CP30210 to its existing Gemini Notebook without re-uploading (decision D4) | ⚪ `open` | `-` | `-` | - | - | **TODO**: D4 已回覆：心理學研究法也要學習網頁等新產出，但使用者 2026-11-25 決定先暫停（耗額度與 token），等使用者說要做再開始。 規格：docs/specs/024-link-record-only-course-to-existing-notebook.md（Draft，暫停中）。 |

<!-- LIVE_STATE_END -->

## 📜 交接與活動時間軸 (Handoff & Activity Timeline)

### [2026-11-26 01:02 UTC] 完成任務 `TASK-043` — Deprecate migrate-study-layout in favour of consolidate (decision D5) (by `claude-code`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: SPEC-023: migrate-study-layout retired (HTTP 410, MCP tool and service removed, ADR-018) after user approval on 2026-11-26.

### [2026-11-26 01:02 UTC] 完成任務 `TASK-042` — Investigate blocked Playwright sign-in and move it to real Chrome + CDP (decision D3) (by `claude-code`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: SPEC-022: Gemini Notebook sign-in and literature browser run in real Chrome over CDP (ADR-017); user verified sign-in and Cloudflare pass on 2026-11-26; ISSUE-043 resolved.

### [2026-11-25 11:20 UTC] 認領任務 `TASK-040` (Learning-site artifacts (per lecture and whole book) via Gemini Notebook chat and Studio download) (by `claude-code`)
- **相關範圍**: `docs/specs/021-learning-site-artifacts.md, docs/superpowers/plans/2026-11-25-learning-site-artifacts.md`
- **延續待辦事項**: 依 docs/superpowers/plans/2026-11-25-learning-site-artifacts.md 實作 Task 1–6（SPEC-021）。Task 6 Step 2 真實資料驗收會用 Gemini Notebook 額度，需使用者同意。

### [2026-11-25 09:09 UTC] 交接：下一個對話的總實作計畫 (by `claude-code`)
- **開工先讀**：`docs/superpowers/plans/2026-11-25-next-session-master-plan.md`（狀態快照、決策 D1–D6、工作項目 W1–W7、注意事項）
- **主要工作**：TASK-040 學習網頁產出，計畫 `docs/superpowers/plans/2026-11-25-learning-site-artifacts.md`（SPEC-021）
- **待決策任務**：TASK-041（心理學研究法連結筆記本）、TASK-042（Playwright 被擋）、TASK-043（停用 migrate-study-layout）
- **未推送**：5 筆 commit（5c6ac66、2f23fe8、7e7aa65、dae1dcd、08265f1）＋本次交接 commit，需使用者同意
- **基準**：540 項測試 OK、agentctl check 0 警告、scan 100/100

### [2026-11-25 09:09 UTC] 建立任務 `TASK-043`: Deprecate migrate-study-layout in favour of consolidate (decision D5) (by `system`)
- **狀態**: `open`
- **相關範圍**: `-`

### [2026-11-25 09:09 UTC] 建立任務 `TASK-042`: Investigate blocked Playwright sign-in and move it to real Chrome + CDP (decision D3) (by `system`)
- **狀態**: `open`
- **相關範圍**: `-`

### [2026-11-25 09:09 UTC] 建立任務 `TASK-041`: Link 115-1_CP30210 to its existing Gemini Notebook without re-uploading (decision D4) (by `system`)
- **狀態**: `open`
- **相關範圍**: `-`

### [2026-11-25 08:49 UTC] 建立任務 `TASK-040`: Learning-site artifacts (per lecture and whole book) via Gemini Notebook chat and Studio download (by `system`)
- **狀態**: `open`
- **相關範圍**: `docs/specs/021-learning-site-artifacts.md, docs/superpowers/plans/2026-11-25-learning-site-artifacts.md`

### [2026-11-25 05:13 UTC] 完成任務 `TASK-037` — Textbook chapters as lecture source and auto-split full textbooks in 01 Materials (by `claude-code`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: SPEC-018: pypdf textbook chapter split (ported literature-parser rules, names match all 16 existing chapter PDFs), .textbook.json chapter folders as lecture source when 02 Handouts is empty, relocate misfiled chapters keeping lecture numbers. Real-data relocate is dry-run only, pending user (TASK-036 #18).

### [2026-11-25 05:13 UTC] 完成任務 `TASK-038` — Backlog: course display-name edit, NoteStudio extra files, completion notification, backup retention (by `claude-code`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: SPEC-016 display-name edit + SPEC-017 note-files browser, course-complete macOS notification, _vN versioned adoption, backup pruning (moves to deleted/backups). 529 tests, check 0 warnings.

### [2026-11-25 05:13 UTC] 完成任務 `TASK-039` — Wire study-library registration, archive/restore and scratch filing into the web UI (rule 13) (by `claude-code`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: SPEC-016: web entry points for registering past/non-standard course folders, scratch filing/unfiling, and course display-name edits (HTTP/MCP/web); browser-verified on real data.

### [2026-11-25 04:37 UTC] 記錄待辦：TASK-036～039 (by `claude-code`)
- **TASK-036**：使用者實機確認與整理清單（`.agents/tasks/TASK-036-checklist.md`，17 項實機確認＋4 項整理）
- **TASK-037**：課本章節作為講次來源＋01 Materials 整本課本自動切割（移植 literature-parser 的 analyzer/splitter，改用 pypdf）
- **TASK-038**：小功能待辦（改課程顯示名稱、NoteStudio 非章節檔、完成通知、多版本反查、備份保留策略）
- **TASK-039**：核心規則 13 缺口——學習資料夾掃描／批次登錄舊課／scratch 歸檔／封存還原在網頁沒有入口
- **資料異動**：115-1_CP31000 的 name、subject 已改為 `生涯諮商與實務`（備份 `backups/db-20261125-115355`、`db-20261125-122559`）

### [2026-11-25 04:35 UTC] 建立任務 `TASK-039`: Wire study-library registration, archive/restore and scratch filing into the web UI (rule 13) (by `system`)
- **狀態**: `open`
- **相關範圍**: `src/notebooklm_batch_studio/entrypoints/static, src/notebooklm_batch_studio/entrypoints/http/study_library.py`

### [2026-11-25 04:34 UTC] 建立任務 `TASK-038`: Backlog: course display-name edit, NoteStudio extra files, completion notification, backup retention (by `system`)
- **狀態**: `open`
- **相關範圍**: `-`

### [2026-11-25 04:34 UTC] 建立任務 `TASK-037`: Textbook chapters as lecture source and auto-split full textbooks in 01 Materials (by `system`)
- **狀態**: `open`
- **相關範圍**: `src/notebooklm_batch_studio/services/course_parser.py, src/notebooklm_batch_studio/config/study_layout.py, src/notebooklm_batch_studio/services/job_planner.py`

### [2026-11-25 04:34 UTC] 建立任務 `TASK-036`: User manual verification and housekeeping checklist (by `system`)
- **狀態**: `open`
- **相關範圍**: `-`

### [2026-11-25 01:08 UTC] 完成任務 `TASK-035` — Study library, course identity and learning record (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Completed SPEC-014 study library unification, learning record, legacy consolidation, SPEC-015 adopt_existing_outputs, ISSUE-068 guard, demo update, and Task 17 documentation closeout.
- **交接備註**: 本機 `main` 尚有未推送 commits 等待使用者確認後推送；`agentctl update` 依使用者指示暫緩至計畫結束後處理；使用者實機確認清單已列於 Task 17 回報。

### [2026-11-24 09:21 UTC] 建立任務 `TASK-035`: Study library, course identity and learning record (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-24 09:19 UTC] Session Closeout (結束對話收尾) (by `antigravity`)
- **檢查結果**: 測試與 Code Review Guard 通過
- **目標**: Complete evidence-backed record/spec/MCP audit (TASK-033), port Gemini Web auth (TASK-031/ISSUE-053), fix literature stale-job cleanup and cross-process RunLock
- **錯誤與根因**: ISSUE-053 (missing Gemini Web login entrypoint -> ported GeminiAuthService + 3-entrypoint login); ISSUE-054 (leftover running literature_jobs -> startup close_s
- **下一步**: Proceed with real-machine/browser verification items marked 待實機 in SPEC-001..011 or review Claude Code's untracked plan docs/superpowers/plans/2026-11-24-study-
- **交接備註**: All 441 tests pass, agentctl check 0 warnings, agentctl scan 100/100; TASK-031..034 closed and pushed
- **本機對話紀錄**: `.agents/conversations/2026-11-24-1719-antigravity-summary.md`（只在這台電腦）

### [2026-11-24 08:59 UTC] 完成任務 `TASK-034` — Fix ISSUE-054 regression: guard literature stale-job cleanup with RunLock (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Ported RunLock (fcntl.flock) to adapters/locks.py, added AppConfig.literature_job_lock_path, guarded LiteratureJobRunner stale cleanup & job execution with cross-process lock, and wired api.py and mcp_extensions.py (ISSUE-057).

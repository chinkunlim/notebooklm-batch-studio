# 🤝 Agent 狀態看板與交接紀錄 (`LATEST.md`)

> **AI Agent 開工必讀**：進入對話時請先閱讀下方「即時狀態看板」，確認上一位 Agent 的完成進度、待接手任務 (`handed_off`) 與注意事項；詳細過程請看本機的 `.agents/conversations/`。

<!-- LIVE_STATE_START -->
## 📊 即時狀態看板 (Live Snapshot)

- **最後更新時間**: `2026-11-25 04:37 UTC`
- **最近操作 Agent**: `claude-code`
- **目前 Git 分支**: `main`
- **最新 Git Commit**: `6985bf2 fix(study): keep courses already in study root during layout migration (ISSUE-069) [agent:claude-code]`

### 🎯 進行中 / 待接手任務 (Active & Handed-Off Tasks)

| 任務 | 狀態 | 目前/上一位 Agent | 建議接手 | 相關範圍 | 已完成 | 待辦與卡點 |
|---|---|---|---|---|---|---|
| **TASK-036**<br/>User manual verification and housekeeping checklist | ⚪ `open` | `-` | `-` | - | - | **TODO**: 使用者實機確認與整理清單，見 .agents/tasks/TASK-036-checklist.md（逐項勾選並附證據）。 |
| **TASK-037**<br/>Textbook chapters as lecture source and auto-split full textbooks in 01 Materials | ⚪ `open` | `-` | `-` | `src/notebooklm_batch_studio/services/course_parser.py`, `src/notebooklm_batch_studio/config/study_layout.py`, `src/notebooklm_batch_studio/services/job_planner.py` | - | **TODO**: SDD→BDD→TDD 新規格（SPEC-016）。使用者決定：02 Handouts 只放老師講義；完整課本 PDF 放 01 Materials/，切割後自動建立 01 Materials/<課本名>/ 子資料夾放各章 PDF。(1) 移植 literature-parser 的章節偵測：services/core/analyzer.py PDFAnalyzer.get_sections（書籤優先、無書籤時掃頁首文字；front_matter_taxonomy.json 前言分類）與 services/core/splitter.py PDFSplitter.split_chapter（頁碼範圍切割並保留該章書籤）；改用本專案已有的 pypdf（BSD），不要引入 pymupdf（AGPL）與 pdfseparate/pdfunite CLI；依本專案分層與註解規範重寫，純計算放 domain。(2) 切割預設 dry-run 預覽（章名、頁碼範圍、輸出檔名 ChNN-Title.pdf），確認後才寫檔；原始整本 PDF 保留不動；同名不覆寫。(3) 每門課新增『講次來源』設定：handouts（預設）\| textbook_chapters \| both；course_parser 依設定掃描 02 Handouts 或 01 Materials/<課本名>/。(4) 既有兩門課（115-1_CP31000 10 章、115-1_CP30210 6 章）的章節 PDF 目前誤放在 02 Handouts：提供 dry-run 搬移到 01 Materials/<課本名>/，保留 lecture_no 與 sha256，只更新 lectures.category/relative_path，142 筆 done 工作與 03 Notes 產出不受影響；真實資料先停在 dry-run 等使用者確認。(5) 三入口：HTTP、MCP（confirm）、網頁。(6) watcher：01 Materials 頂層出現新整本 PDF 時只提示可切割，不自動寫檔。 |
| **TASK-038**<br/>Backlog: course display-name edit, NoteStudio extra files, completion notification, backup retention | ⚪ `open` | `-` | `-` | - | - | **TODO**: 小功能待辦：(1) 修改課程顯示名稱（HTTP/MCP/網頁；目前只能直接改 DB，2026-11-25 已手動把 115-1_CP31000 改為 生涯諮商與實務）；(2) NoteStudio 非章節檔瀏覽：00_總覽與跨章整合筆記.md、學習筆記/PDF/*.pdf、章節/**/目前/（SPEC-015 §6 後續待辦 ②）；(3) 全部產出完成時 macOS 通知（SPEC-001 未實作）；(4) adopt_existing_outputs 反查 *_v2 等多版本產出；(5) DATA_DIR/backups 保留策略（例如只留最近 N 份，update.sh 備份後清理），刪除前須使用者確認。 |
| **TASK-039**<br/>Wire study-library registration, archive/restore and scratch filing into the web UI (rule 13) | ⚪ `open` | `-` | `-` | `src/notebooklm_batch_studio/entrypoints/static`, `src/notebooklm_batch_studio/entrypoints/http/study_library.py` | - | **TODO**: 核心規則 13 缺口：下列功能只有 HTTP 與 MCP，網頁沒有入口——GET /api/study/library（掃描學習資料夾）、POST /api/study/library/register（批次登錄舊課 record-only）、POST /api/study/library/register-folder（非標準資料夾手動填課號）、GET /api/study/unfiled、POST /api/study/file、POST /api/study/unfile（scratch 歸檔）、POST /api/courses/{code}/archive 與 /restore（封存／還原，先封存才可刪除）。在網頁『學習紀錄』或課程進階工具加入對應介面，先預覽再確認；TDD，含瀏覽器驗證。 |

<!-- LIVE_STATE_END -->

## 📜 交接與活動時間軸 (Handoff & Activity Timeline)

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

### [2026-11-24 08:56 UTC] 建立任務 `TASK-034`: Fix ISSUE-054 regression: guard literature stale-job cleanup with RunLock (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-24 08:18 UTC] 完成任務 `TASK-033` — Audit records, unify MCP confirm format, and document cross-repo decisions (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Audited SPEC/ADR/ISSUE/TASK/CHANGELOG traceability with verifiable command/git/line evidence, mapped note-studio & literature-fetch cross-repo refs, documented StepValidator/calculate_outline_words/unported tests decisions, unified all 25 mutating MCP confirm=False payloads via mcp_confirm.py, and verified SPEC acceptance criteria.

### [2026-11-24 08:04 UTC] 建立任務 `TASK-033`: Audit records, unify MCP confirm format, and document cross-repo decisions (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-24 08:04 UTC] 完成任務 `TASK-032` — Resolve ISSUE-054: close stale running literature jobs on startup (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Closed stale running literature_jobs as failed on LiteratureJobRunner startup, handled BaseException in worker, and ported StaleJobTest (ISSUE-054)

### [2026-11-24 08:02 UTC] 建立任務 `TASK-032`: Resolve ISSUE-054: close stale running literature jobs on startup (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-24 08:02 UTC] 完成任務 `TASK-031` — Resolve ISSUE-053: port Gemini Web auth service and 3-entrypoint login (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Ported GeminiAuthService, ChromeGeminiLoginRuntime, HTTP/MCP/Web login entrypoints, and test_gemini_auth.py; updated browser_session.py error guidance (ISSUE-053)

### [2026-11-24 07:58 UTC] 建立任務 `TASK-031`: Resolve ISSUE-053: port Gemini Web auth service and 3-entrypoint login (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-24 05:48 UTC] 完成任務 `TASK-030` — Close security hardening, HTTP 400, XSS, and MCP confirm gaps from Claude review (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Closed path-safety gaps (import_legacy, source_manager), notes HTTP 400 handling, frontend XSS/escHtml/URL guards, and unified MCP confirm format with synced specs

### [2026-11-24 05:43 UTC] 建立任務 `TASK-030`: Close security hardening, HTTP 400, XSS, and MCP confirm gaps from Claude review (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-24 02:25 UTC] 完成任務 `TASK-029` — Records audit, port source-project tests, full verification (by `claude-code`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Records audit (gaps listed for Antigravity), ported 52 source-project tests (note-studio gemini adapters, quota parser, literature-fetch markdown/db) plus 13 new pipeline behavior tests, fixed ISSUE-052/055/056, recorded open ISSUE-053/054, full verification

### [2026-11-24 02:20 UTC] 建立任務 `TASK-029`: Records audit, port source-project tests, full verification (by `claude-code`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

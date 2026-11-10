# 🤝 Agent 狀態看板與交接紀錄 (`LATEST.md`)

> **AI Agent 開工必讀**：進入對話時請先閱讀下方「即時狀態看板」，確認上一位 Agent 的完成進度、待接手任務 (`handed_off`) 與注意事項；詳細過程請看本機的 `.agents/conversations/`。

<!-- LIVE_STATE_START -->
## 📊 即時狀態看板 (Live Snapshot)

- **最後更新時間**: `2026-11-10 03:08 UTC`
- **最近操作 Agent**: `antigravity`
- **目前 Git 分支**: `main`
- **最新 Git Commit**: `a01ee0c docs(docs/issues): update docs/issues documentation (ADR-009, ISSUE-025, ISSUE-028, ISSUE-029, ISSUE-030, ISSUE-031, ISSUE-032, ISSUE-033, TASK-006, TASK-007, TASK-011, TASK-012, TASK-013) [agent:claude-code]`

### 🎯 進行中 / 待接手任務 (Active & Handed-Off Tasks)

| 任務 | 狀態 | 目前/上一位 Agent | 建議接手 | 相關範圍 | 已完成 | 待辦與卡點 |
|---|---|---|---|---|---|---|
| **TASK-012**<br/>Course filter in 課程目錄: all / in progress / finished | ⚪ `open` | `-` | `-` | `src/notebooklm_batch_studio/entrypoints/static/studio-app.js`, `src/notebooklm_batch_studio/entrypoints/http/courses.py` | - | **TODO**: v05 showed a 全部 / 進行中 / 已完成 filter above 我的課程 (課程目錄). Removed at migration because the backend has no rule for a course's study state. To do: define 進行中 / 已完成 (e.g. every lecture's plan steps done = 已完成; any study activity = 進行中), expose it on GET /api/courses (or the plan), add the seg back in renderCourseDirectory (studio-app.js) and remember the choice as a preference. Test the rule in tests/. |
| **TASK-013**<br/>Apply one course's settings to other courses | ⚪ `open` | `-` | `-` | `src/notebooklm_batch_studio/services/course_settings.py`, `src/notebooklm_batch_studio/entrypoints/http/settings.py`, `src/notebooklm_batch_studio/entrypoints/mcp_course_settings.py`, `src/notebooklm_batch_studio/entrypoints/static/studio-settings.js` | - | **TODO**: v05 showed 「套用到其他課程」 in the course settings. Removed at migration: no endpoint copies settings between courses. To do: service method in course_settings.py that copies GenerationOptions + language / mock exam count (not the exam date) to chosen courses; POST /api/courses/{code}/options/copy {targets: [...]}; MCP tool copy_course_options(code, targets, confirm); a dialog in studio-settings.js to pick target courses; tests for the copy and the confirm guard. |
| **TASK-014**<br/>Fix incomplete course deletion cleanup (DB tables, preferences, and study UI state) | ⚪ `open` | `-` | `-` | `src/notebooklm_batch_studio/adapters/db/repository.py`, `src/notebooklm_batch_studio/entrypoints/static/studio-app.js`, `src/notebooklm_batch_studio/entrypoints/static/studio-batch.js`, `src/notebooklm_batch_studio/entrypoints/static/studio-bench.js`, `src/notebooklm_batch_studio/entrypoints/static/studio-reader.js`, `src/notebooklm_batch_studio/entrypoints/static/studio.js`, `tests/test_course_settings.py` | - | **TODO**: Refs: ISSUE-034. Keep moving output files to DATA_DIR/deleted/. (1) Backend CourseRepository.delete_course(code): also delete KeyPointsRecord, TutorMessageRecord, and course-specific UiPreferenceRecord keys (place:<code>, examNotice:<code>, audio:<code>:%, and course == code). (2) Frontend: on deleteCourse(code), forget course preferences and reset #activeJobs; when currentCoursesList.length === 0 in initStudyPortal(), reset currentStudyCourse = null, activeStudyLectureNo = null, studyHistory = [], studyMistakes = [] and clear all study/overview/review DOM panels (top-bar picker, 課程目錄 right pane, breadcrumbs, PDF reader, audio player, side keypoints, workbench panels, 研讀總覽, 弱點複習). (3) Add regression tests in tests/test_course_settings.py. |
| **TASK-015**<br/>Fix WorkerPool blocked_quota_types permanent stall on resume and empty quota_wait | ⚪ `open` | `-` | `-` | `src/notebooklm_batch_studio/services/worker_pool.py`, `src/notebooklm_batch_studio/services/orchestrator.py`, `src/notebooklm_batch_studio/adapters/db/repository.py`, `src/notebooklm_batch_studio/domain/repositories.py`, `tests/test_worker_pool.py` | - | **TODO**: Refs: ISSUE-035. (1) WorkerPool.resume() must call self.blocked_quota_types.clear(). (2) WorkerPool._quota_probe_loop() must also clear self.blocked_quota_types (or prune types with no active QUOTA_WAIT jobs in DB) when awakened == 0 so deleting a course or retrying jobs never leaves blocked_quota_types stuck in memory. (3) QueueRepository.refresh_quota_wait(artifact_type=None, force=False) should support force=True for manual resume_quota_wait(), and BatchStudioService.resume_quota_wait() / retry_job() should clear the corresponding types from worker_pool.blocked_quota_types. (4) Add unit tests in tests/test_worker_pool.py. |
| **TASK-016**<br/>Fix course overall output progress not updating and exclude skipped jobs from progress_percent | ⚪ `open` | `-` | `-` | `src/notebooklm_batch_studio/services/orchestrator.py`, `src/notebooklm_batch_studio/entrypoints/static/studio-batch.js`, `src/notebooklm_batch_studio/entrypoints/static/studio-start.js`, `tests/test_course_settings.py` | - | **TODO**: Refs: ISSUE-036. (1) Backend orchestrator.py (list_courses_summary & get_course_detail): exclude skipped jobs from active total when computing progress_percent. (2) Frontend studio-batch.js / studio-start.js: when queue counts change in fetchStatus() (or during the 15s poll / after syncFromNotebookLM / retryUpload / regenerateArtifact), call fetchCourses() so #courseContainer cards, top-bar #coursePick, and 課程目錄 #courseList update their overall progress; also refresh currentStudyCourse and loadTodayPanel() when done count increases; filter out skipped jobs in renderStatusBar(). (3) Add regression test in tests/test_course_settings.py. |
| **TASK-017**<br/>Dummy-mode end-to-end chaos & foolproof test suite (simulate naive user exploring all features with mock files) | ⚪ `open` | `-` | `-` | `tests/`, `src/notebooklm_batch_studio/entrypoints/static/`, `tests/fixtures/` | - | **TODO**: Simulate a naive / chaos user exploring and stress-testing ALL studio features offline with dummy files (no real NotebookLM needed). (1) Fixtures: prepare dummy files for all 12 artifact types (PDF, MP3, Quiz JSON, Markdown guides/reports, OPML/JSON mind maps, PNG infographics, CSV tables, mock video). (2) Chaos user journeys: (a) Empty & zero states: click every button/tab/picker in overview, study studio, review, batch before adding courses, and after deleting the only course; (b) Batch operations: add empty/invalid folders, toggling artifact picks, rapid start/pause/resume/wake, delete course while busy, prompt editing with extremes; (c) Study studio: test all 4 workbench arrangements, drag reordering, unpinning all items, layout switching (stage/split/stack), turntable player with missing audio, pdf reader with missing pdf, quiz with 0 answers / all wrong / all right, flashcard rating, tutor spamming; (d) Review & Overview: clear all mistakes, Leitner box transitions, exam countdown with extreme/past dates; (e) Settings & Customization: rapid palette/font switching, extreme custom palette, dark mode toggling. (3) Deliverable: automated dummy-mode simulation test suite in tests/ (e.g. tests/test_dummy_user_simulation.py) verifying zero crashes and 100% graceful degradation. |
| **TASK-018**<br/>Analyze graphify report and project workflow for code alignment and entanglement | 🟢 `in_progress` | `antigravity` | `-` | `graphify-out/GRAPH_REPORT.md`, `docs/specs/010-user-end-to-end-workflow.md`, `docs/architecture/WORKFLOW_AND_COUPLING_ANALYSIS.md`, `src/notebooklm_batch_studio/services/orchestrator.py`, `src/notebooklm_batch_studio/services/worker_pool.py`, `src/notebooklm_batch_studio/entrypoints/static/` | 1. Completed deep analysis of graphify report (9270 nodes, 18667 edges, 392 communities, vendor noise vs core hubs).\n2. Identified four system entanglements: God Service (BatchStudioService), frontend 12-script global state spaghetti, job planning mixed into worker pool, and dual-state desynchronization (memory vs DB).\n3. Audited codebase conformance against SPEC-010 8-stage workflow (revealing gaps in phase 4 progress/quota recovery and phase 8 course deletion).\n4. Formulated decoupling & streamlining blueprint (StudioBus, service triage, SSOT) in docs/architecture/WORKFLOW_AND_COUPLING_ANALYSIS.md. | **TODO**: Execute refactoring according to tasks: TASK-014 (delete cleanup), TASK-015 (worker quota unblock), TASK-016 (progress update), TASK-017 (chaos test), followed by front/backend decoupling. |
| **TASK-019**<br/>Audit all resolved known issues with verification evidence and exclude vendor noise from graphify | 🟢 `in_progress` | `antigravity` | `-` | - | - | - |

<!-- LIVE_STATE_END -->

## 📜 交接與活動時間軸 (Handoff & Activity Timeline)

### [2026-11-10 03:08 UTC] 認領任務 `TASK-019` (Audit all resolved known issues with verification evidence and exclude vendor noise from graphify) (by `antigravity`)
- **相關範圍**: `-`
- **接棒自**: `antigravity`

### [2026-11-10 03:08 UTC] 建立任務 `TASK-019`: Audit all resolved known issues with verification evidence and exclude vendor noise from graphify (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-10 03:05 UTC] 認領任務 `TASK-018` (Analyze graphify report and project workflow for code alignment and entanglement) (by `antigravity`)
- **相關範圍**: `-`
- **接棒自**: `antigravity`

### [2026-11-10 03:05 UTC] 建立任務 `TASK-018`: Analyze graphify report and project workflow for code alignment and entanglement (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-10 02:56 UTC] 建立任務 `TASK-017`: Dummy-mode end-to-end chaos & foolproof test suite (simulate naive user exploring all features with mock files) (by `system`)
- **狀態**: `open`
- **相關範圍**: `tests/, src/notebooklm_batch_studio/entrypoints/static/, tests/fixtures/`

### [2026-11-09 09:21 UTC] 建立任務 `TASK-016`: Fix course overall output progress not updating and exclude skipped jobs from progress_percent (by `system`)
- **狀態**: `open`
- **相關範圍**: `src/notebooklm_batch_studio/services/orchestrator.py, src/notebooklm_batch_studio/entrypoints/static/studio-batch.js, src/notebooklm_batch_studio/entrypoints/static/studio-start.js, tests/test_course_settings.py`

### [2026-11-09 08:10 UTC] 建立任務 `TASK-015`: Fix WorkerPool blocked_quota_types permanent stall on resume and empty quota_wait (by `system`)
- **狀態**: `open`
- **相關範圍**: `src/notebooklm_batch_studio/services/worker_pool.py, src/notebooklm_batch_studio/services/orchestrator.py, src/notebooklm_batch_studio/adapters/db/repository.py, src/notebooklm_batch_studio/domain/repositories.py, tests/test_worker_pool.py`

### [2026-11-09 08:06 UTC] 建立任務 `TASK-014`: Fix incomplete course deletion cleanup (DB tables, preferences, and study UI state) (by `system`)
- **狀態**: `open`
- **相關範圍**: `src/notebooklm_batch_studio/adapters/db/repository.py, src/notebooklm_batch_studio/entrypoints/static/studio-app.js, src/notebooklm_batch_studio/entrypoints/static/studio-batch.js, src/notebooklm_batch_studio/entrypoints/static/studio-bench.js, src/notebooklm_batch_studio/entrypoints/static/studio-reader.js, src/notebooklm_batch_studio/entrypoints/static/studio.js, tests/test_course_settings.py`

### [2026-11-02 12:59 UTC] Session Closeout (結束對話收尾) (by `claude-code`)
- **檢查結果**: 測試與 Code Review Guard 通過
- **目標**: Apply the approved v05 design to the real web UI, then refine it with the user: local preferences, offline icons/fonts, font pairings, overview check-in and exa
- **錯誤與根因**: Safari sidebar gap -> sticky + 100vh/dvh measured differently in Safari -> position fixed top/bottom 0 (ISSUE-031); page-switch jank -> View Transitions snapsho
- **下一步**: User enables GitHub Pages (Settings -> Pages -> main /docs) to publish docs/demo/; open backlog TASK-012 (course filter) and TASK-013 (apply settings to other c
- **交接備註**: v05 is live and pushed; 183 tests pass; demo at docs/demo/index.html verified in Chromium and WebKit
- **本機對話紀錄**: `.agents/conversations/2026-11-02-2059-claude-code-summary.md`（只在這台電腦）

### [2026-11-02 12:58 UTC] 完成任務 `TASK-011` — Apply v05 design to the web UI (by `claude-code`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: (無)

### [2026-11-02 07:31 UTC] 建立任務 `TASK-013`: Apply one course's settings to other courses (by `system`)
- **狀態**: `open`
- **相關範圍**: `src/notebooklm_batch_studio/services/course_settings.py, src/notebooklm_batch_studio/entrypoints/http/settings.py, src/notebooklm_batch_studio/entrypoints/mcp_course_settings.py, src/notebooklm_batch_studio/entrypoints/static/studio-settings.js`

### [2026-11-02 07:31 UTC] 建立任務 `TASK-012`: Course filter in 課程目錄: all / in progress / finished (by `system`)
- **狀態**: `open`
- **相關範圍**: `src/notebooklm_batch_studio/entrypoints/static/studio-app.js, src/notebooklm_batch_studio/entrypoints/http/courses.py`

### [2026-11-02 04:24 UTC] 建立任務 `TASK-011`: Apply v05 design to the web UI (by `claude-code`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-01 18:07 UTC] Session Closeout (結束對話收尾) (by `claude-code`)
- **檢查結果**: 測試與 Code Review Guard 通過
- **目標**: Audit all Markdown records after alternating Claude Code and Antigravity sessions, fill gaps, and push
- **錯誤與根因**: Four root-caused bugs from the Claude session had no records -> added ISSUE-027 (port check without SO_REUSEADDR misread TIME_WAIT as busy), ISSUE-028 (StaticFi
- **下一步**: Implement SPEC-009 (docs/specs/009-study-studio-ui-redesign.md, prototypes in docs/design/) after the user confirms; midterm deliverables are in DATA_DIR/midter
- **交接備註**: All records reconciled across Claude Code and Antigravity sessions; 173 tests pass
- **本機對話紀錄**: `.agents/conversations/2026-11-02-0207-claude-code-summary.md`（只在這台電腦）

### [2026-11-01 18:02 UTC] Session Closeout (結束對話收尾) (by `antigravity`)
- **檢查結果**: 測試與 Code Review Guard 通過
- **目標**: 研讀工作室介面重構設計、奢華黑膠擬態留聲機、九宮格矩陣、RWD 根治與完整歷史版本歸檔
- **錯誤與根因**: ISSUE-026：桌面環境點選 iPhone (416) 模擬器時，因視窗本體未達門檻而未觸發 @media (max-width: 500px) 導致排版與縮放失效 -> 改採 @media (max-width: 680px), [data-device="iphone"] 雙軌選擇器根治
- **下一步**: 由 Claude Code 讀取 docs/specs/SPEC-009-STUDY-STUDIO-UI-REDESIGN.md 與 designs_archive/ 進行正式程式碼移植
- **交接備註**: UI 重構規格 SPEC-009、ADR-007、ISSUE-026 與 Version 1~4 原型歸檔已 100% 備妥，src/ 保持零改動，待 Claude 接手實作
- **本機對話紀錄**: `.agents/conversations/2026-11-02-0202-antigravity-summary.md`（只在這台電腦）

### [2026-11-01 15:08 UTC] Session Closeout (結束對話收尾) (by `antigravity`)
- **檢查結果**: 測試與 Code Review Guard 通過
- **目標**: Diagnose GitHub Actions CI failure and fix Linux TCP socket TIME_WAIT test issue (ISSUE-025)
- **錯誤與根因**: CI failed on Ubuntu runner in test_recently_closed_port_is_free -> Linux kernel requires prior socket to have SO_REUSEADDR set before bind to allow subsequent T
- **下一步**: CI is now 100% green; submit midterm course deliverables and repo URL to course portal
- **交接備註**: Resolved GitHub Actions CI failure (ISSUE-025), tests green across both Linux and macOS
- **本機對話紀錄**: `.agents/conversations/2026-11-01-2308-antigravity-summary.md`（只在這台電腦）

### [2026-11-01 14:57 UTC] Session Closeout (結束對話收尾) (by `antigravity`)
- **檢查結果**: 測試與 Code Review Guard 通過
- **目標**: Complete midterm project deliverables: generate real batch outputs, produce Word/PDF report, 12-slide PPTX/PDF with speaker notes, AI collaboration summary, and
- **錯誤與根因**: Keynote rejected PPTX notes slide due to missing notesMaster in default python-pptx -> resolved by generating clean PPTX and using Keynote AppleScript to inject
- **下一步**: Submit repo link and 4 files to course portal. Repo needs to be toggled to Public in GitHub settings by user. All 173 tests pass and queue continues in backgrou
- **交接備註**: Midterm deliverables 100% complete in DATA_DIR/midterm-submission/ with report, slides with notes, AI summary, and walkthrough video.
- **本機對話紀錄**: `.agents/conversations/2026-11-01-2257-antigravity-summary.md`（只在這台電腦）

### [2026-11-01 13:12 UTC] Session Closeout (結束對話收尾) (by `antigravity`)
- **檢查結果**: 測試與 Code Review Guard 通過
- **目標**: Audit and synchronize all repository Markdown documentation with Claude's recent code and architecture updates
- **錯誤與根因**: Documentation lagged behind Claude's 10 recent commits (SPEC-006~008, 8 new DB tables, Design v2, learning aids) -> verified and synchronized all md files acros
- **下一步**: System and documentation 100% synchronized and verified; all 173 tests pass; user can test web dashboard or batch pipeline
- **交接備註**: All documentation, architecture diagrams, specs, ADRs, known issues, DB schemas, and test suites are 100% synchronized.
- **本機對話紀錄**: `.agents/conversations/2026-11-01-2112-antigravity-summary.md`（只在這台電腦）

### [2026-11-01 13:10 UTC] 全專案 Markdown 文件同步與檢查 (by `antigravity`)
- **檢查結果**: 173 項單元與整合測試 100% 通過、Code Review Guard 通過、Alembic Check 與 Ruff / Mypy 通過
- **目標**: 全面審查並同步全專案所有 Markdown 文件（ARCHITECTURE.md, alembic/DB.md, README.md, PROJECT_RULES.md, LATEST.md），使之與 Claude 最新 10 個 Commit 擴充之功能完全一致
- **錯誤與根因**: Claude 大幅擴充了 SPEC-006（獨立產出設定）、SPEC-007（學生研讀計畫）、SPEC-008（學習心理學與 PDF 閱讀器）、Alembic 新增 8 張資料表、Design v2 UI 與修正 016~024，但 ARCHITECTURE.md、alembic/DB.md、README.md 索引與 PROJECT_RULES 未同步更新 -> 本次全面補齊架構層次、Mermaid 圖、11 張實體資料表綱要與業務工作流程
- **下一步**: 所有程式碼與 100% 文件皆已同步無缺，可直接執行 `uv run notebooklm-batch-studio web` 或雙擊 macOS 一鍵 Launcher 進行端對端驗證
- **交接備註**: 全專案所有規格（SPEC-001 ~ 008）、架構決策（ADR-001 ~ 006）、已知問題（ISSUE-001 ~ 024）與文檔結構 100% 同步

### [2026-11-01 12:45 UTC] 學習輔助功能與系統全面大更新 (by `claude-code`)
- **檢查結果**: 173 項測試全數通過
- **主要內容**:
  1. SPEC-006: 各產出項目獨立規格自訂（題量、難度、投影片格式等）與三層設定繼承
  2. SPEC-007: 學生研讀工作台 Today 計畫、考前倒數、跨講混合複習與 AI 詳解保存
  3. SPEC-008: 內建離線 PDF.js 講義閱讀器、Gemini Notebook 重點萃取畫線、艾賓浩斯半衰期記憶強度計算與連續天數熱圖、作答信心比對（sure-but-wrong 警示）、蘇格拉底式引導家教
  4. Design v2 深色質感介面、macOS Chrome App 全螢幕專注模式一鍵啟動腳本
  5. 已知問題修復：ISSUE-016 ~ ISSUE-024 根治，包含資料庫連線釋放、選項位置打散、Prompt 編輯與立即喚醒按鈕等
  6. 資料庫遷移：新增 `study_progress`, `review_items`, `explanations`, `key_points`, `tutor_messages` 等實體表
- **相關 Commit**: `391057f` ~ `465781e`

# 🤝 Agent 狀態看板與交接紀錄 (`LATEST.md`)

> **AI Agent 開工必讀**：進入對話時請先閱讀下方「即時狀態看板」，確認上一位 Agent 的完成進度、待接手任務 (`handed_off`) 與注意事項；詳細過程請看本機的 `.agents/conversations/`。

<!-- LIVE_STATE_START -->
## 📊 即時狀態看板 (Live Snapshot)

- **最後更新時間**: `2026-11-14 07:47 UTC`
- **最近操作 Agent**: `antigravity`
- **目前 Git 分支**: `main`
- **最新 Git Commit**: `2f91a69 feat(ui,settings): support adding missing artifacts per lecture or course (TASK-022) [agent:antigravity]`

### 🎯 進行中 / 待接手任務 (Active & Handed-Off Tasks)

> 目前無進行中或待接手任務。可執行 `python3 scripts/agentctl.py task create "任務名稱" --agent <name>` 建立任務。

<!-- LIVE_STATE_END -->

## 📜 交接與活動時間軸 (Handoff & Activity Timeline)

### [2026-11-14 07:47 UTC] 完成任務 `TASK-023` — Add notebook source listing, upload, and deletion management (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Added Gemini Notebook source listing, PDF/lecture upload, and source deletion across HTTP, MCP, Web UI, and demo

### [2026-11-14 07:39 UTC] 建立任務 `TASK-023`: Add notebook source listing, upload, and deletion management (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-14 06:10 UTC] 完成任務 `TASK-022` — Support adding missing artifacts per lecture or course and auto-start queue on selection save (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Support adding missing artifacts per lecture or course and auto-start queue on selection save

### [2026-11-14 06:08 UTC] 建立任務 `TASK-022`: Support adding missing artifacts per lecture or course and auto-start queue on selection save (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-14 05:18 UTC] 完成任務 `TASK-021` — Fix failed artifact job manual rerun and automatic retry recovery (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Enable manual UI/HTTP/MCP rerun and automatic cooldown/orphan recovery for failed artifact jobs (ISSUE-038)

### [2026-11-14 05:12 UTC] 建立任務 `TASK-021`: Fix failed artifact job manual rerun and automatic retry recovery (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

### [2026-11-14 04:36 UTC] 完成任務 `TASK-019` — Audit all resolved known issues with verification evidence and exclude vendor noise from graphify (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Resolved and verified with unit/integration tests and zero review_guard violations

### [2026-11-14 04:36 UTC] 完成任務 `TASK-018` — Analyze graphify report and project workflow for code alignment and entanglement (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Resolved and verified with unit/integration tests and zero review_guard violations

### [2026-11-14 04:36 UTC] 完成任務 `TASK-017` — Dummy-mode end-to-end chaos & foolproof test suite (simulate naive user exploring all features with mock files) (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Resolved and verified with unit/integration tests and zero review_guard violations

### [2026-11-14 04:36 UTC] 完成任務 `TASK-016` — Fix course overall output progress not updating and exclude skipped jobs from progress_percent (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Resolved and verified with unit/integration tests and zero review_guard violations

### [2026-11-14 04:36 UTC] 完成任務 `TASK-015` — Fix WorkerPool blocked_quota_types permanent stall on resume and empty quota_wait (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Resolved and verified with unit/integration tests and zero review_guard violations

### [2026-11-14 04:36 UTC] 完成任務 `TASK-014` — Fix incomplete course deletion cleanup (DB tables, preferences, and study UI state) (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Resolved and verified with unit/integration tests and zero review_guard violations

### [2026-11-14 04:36 UTC] 完成任務 `TASK-013` — Apply one course's settings to other courses (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Resolved and verified with unit/integration tests and zero review_guard violations

### [2026-11-14 04:36 UTC] 完成任務 `TASK-012` — Course filter in 課程目錄: all / in progress / finished (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: Resolved and verified with unit/integration tests and zero review_guard violations

### [2026-11-12 16:03 UTC] 完成任務 `TASK-020` — Fix course code collision overwriting existing course and inheriting stale notebook_id (by `antigravity`)
- **狀態**: ✅ 已完成 (`done`)
- **完成摘要**: (無)

### [2026-11-12 10:31 UTC] 建立任務 `TASK-020`: Fix course code collision overwriting existing course and inheriting stale notebook_id (by `antigravity`)
- **狀態**: `in_progress`
- **相關範圍**: `-`

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

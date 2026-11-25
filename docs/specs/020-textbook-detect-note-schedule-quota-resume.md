# SPEC-020：課本偵測、Gemini 筆記背景排程、額度用完到點續跑

- **狀態**：Implemented <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-25
- **相關任務 / ADR**：SPEC-013（NoteStudio 筆記）、SPEC-018（課本切割）、ISSUE-065（Gemini 額度提示解析）、ADR-001

## 1. 目標

使用者定案（2026-11-25）：

1. 把整本課本放進 `01 Materials/` 後，網頁要**自動偵測**並提示，使用者按一下才切割（書籤偶爾判斷錯，保留確認）。
2. Gemini 筆記要能**排程**：使用者選章節按「開始排程」（＝允許），之後在背景一章接一章生成，可暫停／繼續。
3. **不論 Gemini 網頁版還是 Gemini Notebook**，額度用完都要抓重置時間，時間到自動繼續；網頁顯示「預計 HH:MM 繼續」。

現況：課本只能手動切；筆記一次只做一章且會卡住頁面；Gemini 額度用完只標 `quota_wait`、不記重置時間、不會續跑；Gemini Notebook 佇列已會依額度表重置時間續跑，但網頁看不到預計時間。

## 2. 使用情境

- **情境 A**：把《Research Methods…》放進心理學研究法的 `01 Materials/`，批次排程頁出現卡片「偵測到課本：Research Methods….pdf（心理學研究法）・17 章，6 章已存在」，按「預覽並切割」走 SPEC-018 的確認流程；按「略過」後不再提示這本。
- **情境 B**：在筆記生成頁的「筆記排程」選課程，勾選還沒有筆記的章節，按「開始排程」，背景依序生成；頁面顯示每章狀態。
- **情境 C**：生成到第 3 章時 Gemini 顯示額度已用完，排程記下重置時間並顯示「Gemini 額度已滿，預計 18:30 繼續」；時間到從第 3 章未完成的模組接著做。
- **情境 D**：Gemini Notebook 產出佇列額度已滿時，頂部狀態列顯示「額度已滿，預計 HH:MM 繼續」。

## 3. 需求

- **必須 (Must)**：
  1. **課本偵測**：`TextbookService.pending_textbooks(codes)` 列出各修課中課程 `01 Materials` 頂層、尚未切割（章節資料夾沒有 `.textbook.json`）的 PDF，附章數與已存在章數；沒有章節書籤時附錯誤說明。HTTP `GET /api/textbooks/pending`；MCP `list_pending_textbooks`；網頁批次排程頁頂部卡片（每 60 秒更新），「預覽並切割」直接對該本開啟 SPEC-018 預覽，「略過」記在本機偏好 `textbookDismissed`。
  2. **筆記排程**：`NoteScheduler` 以 `DATA_DIR/state/note_schedule.json` 保存排程（原子寫入）。每項：課程、章節、標題、PDF、來源 ID、筆記本 ID、狀態（`pending`／`running`／`quota_wait`／`done`／`failed`）、`resume_at`、`completed_steps`、`last_error`。同一章已在排程中不重複加入。
  3. **背景執行**：網頁服務啟動時（`AUTO_START_QUEUE` 開啟）啟動背景執行緒，依加入順序一次跑一章；伺服器重啟時 `running` 改回 `pending`。排程可暫停／繼續（暫停不中斷正在生成的模組，下一章前停止）。
  4. **Gemini 額度續跑**：`run_chapter` 因額度停止時回傳 `resume_after`（Gemini 提示解析的時間；沒有時預設 1 小時後）；該章標 `quota_wait` 並記下 `resume_at` 與已完成模組；有任何一章在等待額度時，其他章也不開始（同一個 Gemini 帳號）。時間到只重跑未完成的模組（`steps_override`），再縫合成整章。
  5. **Gemini Notebook 預計時間**：`GET /api/status` 新增 `quota_resume_at`（`quota_wait` 工作中最早的 `cooldown_until`）；網頁狀態列顯示「額度已滿，預計 HH:MM 繼續」。
  6. **三入口**：HTTP `GET /api/notes/schedule`、`GET /api/notes/schedule/candidates/{course_key}`、`POST /api/notes/schedule {course_key, lecture_nos}`、`POST /api/notes/schedule/pause`、`POST /api/notes/schedule/resume`、`POST /api/notes/schedule/clear-finished`；MCP `notes_schedule_status`、`notes_schedule_add(…, confirm=False)`、`notes_schedule_pause(confirm)`、`notes_schedule_resume(confirm)`；網頁筆記生成頁「筆記排程」卡片。
- **不做 (Out of scope)**：不自動切割（一律需使用者按）；不用多帳號繞過額度；電腦睡眠或伺服器關閉期間不執行（重開後接著跑）。

## 4. 介面 / API

- `GET /api/notes/schedule` → `{"paused": false, "next_resume_at": "…|null", "items": [...]}`。
- `POST /api/notes/schedule` → `{"added": n, "skipped": m}`；未知課程 404、無講次 422。

## 5. 驗收標準

- [x] **場景 20a**：未切割的課本被列出、已切割與無書籤的情況正確；網頁卡片與略過接上。（`tests/test_auto_schedule.py::test_pending_textbooks_api_and_web`）
- [x] **場景 20b**：加入排程不重複；依序完成；暫停後不開始下一章；伺服器重啟時 running 改回 pending。（`test_scheduler_runs_in_order_pauses_and_recovers`）
- [x] **場景 20c**：額度用完記下 `resume_at` 與完成模組，時間未到不開始任何章，時間到只跑剩下的模組並完成。（`test_quota_wait_resumes_remaining_steps_at_reset_time`）
- [x] **場景 20d**：`/api/status` 回傳 `quota_resume_at`；網頁顯示預計繼續時間；排程三入口與網頁卡片接上。（`test_status_quota_resume_and_schedule_entrypoints`）

## 6. 未決問題

- 無。

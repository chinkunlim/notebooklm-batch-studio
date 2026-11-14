# ISSUE-036：單項產出顯示完成但課程整體產出進度不更新且分母未排除 skipped

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-09
- **解決日期**：2026-11-14
- **Agent**：`antigravity`
- **任務**：`TASK-016`

## 1. 現象

使用者加入課程（提供講義 PDF）後，Gemini Notebook 陸續完成產出，在網頁版下方展開的單講明細或頂部狀態列也顯示「完成」，但：
1. 「批次排程」頁上方的課程卡片整體進度條與百分比（如 `0 / 50　0%`）、頂部課程選單（`產出 0%`）以及「研讀工作室 → 課程目錄」（`產出完成 0%`）都不會推進。
2. 切換到「研讀工作室」或「研讀總覽」時，剛完成的產出物磚塊仍顯示「排隊中／尚未生成」，學習循環與章節路線的步驟晶片仍為灰色的「尚未生成」。
3. 若課程曾取消勾選部分產出物（狀態變為 `skipped`）或從遠端同步（`syncFromNotebookLM`），後端回傳的 `progress_percent` 與狀態統計列總數計算不一致，永遠無法達到 100%。

- **錯誤訊息**：無拋出例外（前端輪詢與操作回呼漏更新課程總表與當前研讀課程；後端百分比分母未扣除 `skipped`）
- **重現步驟**：
  1. 在「批次排程」加入一門課程並啟動佇列生成。
  2. 停留在「批次排程」觀察：下方展開的課程詳情每 15 秒刷新，各講工作列陸續變為「完成」，頂部狀態列也顯示「已完成 N 項」，但上方「已註冊課程」卡片的進度條與百分比完全不動（維持 `0%`）。
  3. 切換到「研讀工作室」或點開頂部課程選單：進度仍顯示 `0%`，工作台磚塊仍顯示舊狀態，必須手動重新整理整個瀏覽器分頁才會更新。
- **影響範圍**：
  - 前端：`src/notebooklm_batch_studio/entrypoints/static/studio-start.js`、`studio-batch.js`、`studio-app.js`
  - 後端：`src/notebooklm_batch_studio/services/orchestrator.py`（`list_courses_summary`、`get_course_detail`）

## 2. 根本原因

1. **前端定時輪詢與操作回呼漏呼叫 `fetchCourses()` 與同步 `currentStudyCourse`**：
   - `studio-start.js` 第 372–376 行的定時器每 5 秒只跑 `fetchStatus()`（僅更新頂部一行文字）、每 15 秒只跑 `viewCourseDetail(activeCourseCode, true)`（僅更新下方展開的單課表格），**從頭到尾沒有呼叫 `fetchCourses()`**。
   - `syncFromNotebookLM()`、`retryUpload()`、`regenerateArtifact()` 完成後也只呼叫 `viewCourseDetail(code)`，沒有呼叫 `fetchCourses()`。
   - 因此全域 `currentCoursesList`、批次頁的 `#courseContainer` 課程卡片、頂部 `#coursePick` 選單與課程目錄 `#courseList` 的整體產出進度永遠停留在頁面剛載入時的數值。
   - 同時，當背景有任務新完成時，`currentStudyCourse` 與 `loadTodayPanel()` 未同步刷新，導致研讀工作室與研讀總覽看不到新完成的產出。
2. **後端 `progress_percent` 與前端 `renderStatusBar` 未排除 `skipped` 任務**：
   - `orchestrator.py` 的 `list_courses_summary()` 與 `get_course_detail()` 以 `total_jobs = sum(raw_counts.values())` 計算 `progress_percent`，未扣除 `JobStatus.SKIPPED`，導致只要有取消勾選的產出項目，`progress_percent` 永遠達不到 100%。
   - `studio-batch.js` 的 `renderStatusBar(jobs, paused)` 直接顯示 `共 ${jobs.length} 項`，未像 `jobGroupsHtml` 一樣過濾掉 `j.status !== 'skipped'`。

## 3. 修正或規避方式

1. **前端輪詢與狀態連動更新**：
   - 在 `studio-batch.js` 的 `fetchStatus()`（或 15 秒輪詢）中，偵測到 `done` / `running` / `pending` 數量與上次不同時，自動呼叫 `fetchCourses()` 更新課程卡片、頂部選單與課程目錄的整體進度；若當前有打開 `activeCourseCode` 則同步刷新 `viewCourseDetail(activeCourseCode, true)`；若 `currentStudyCourse` 存在且完成數有增加，背景刷新 `loadStudyCourseData(currentStudyCourse.code, true)` 與 `loadTodayPanel()`。
   - 在 `viewCourseDetail`、`syncFromNotebookLM`、`regenerateArtifact` 完成後同步更新 `currentCoursesList` 對應課程的統計並重繪課程卡片。
   - `renderStatusBar` 過濾掉 `status === 'skipped'` 的項目，與下方講次分組一致。
2. **後端 `progress_percent` 計算排除 `skipped`**：
   - 在 `orchestrator.py` 的 `list_courses_summary()` 與 `get_course_detail()` 中，有效總數 `active_total = total_jobs - raw_counts.get(JobStatus.SKIPPED.value, 0)`，以 `done_jobs / active_total` 計算 `progress_percent`。
   - 相關程式碼註解加 `Refs: ISSUE-036`。

## 4. 防回歸

- 後端與端對端回歸測試（`tests/test_dummy_user_simulation.py`、`tests/test_selection_and_folders.py`）：驗證含有 `SKIPPED` 任務的課程在其餘任務皆 `DONE` 時，`list_courses_summary` 與 `get_course_detail` 的 `progress_percent` 為 `100.0`。
- 前端輪詢與結構回歸檢查（`tests/test_dummy_user_simulation.py::UiAndStaticRegressionTest`）：驗證 `studio-batch.js`（`renderStatusBar`、`syncLiveCourseProgress`）排除 `skipped` 並於進度變動時刷新課程與研讀視圖。

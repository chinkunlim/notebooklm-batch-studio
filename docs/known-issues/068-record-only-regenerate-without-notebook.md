# ISSUE-068：record-only 課程未連結筆記本時點擊重新生成會失敗

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-25
- **Agent**：`antigravity`
- **任務**：`SPEC-015`

## 1. 現象

透過 `adopt_existing_outputs` 將既有產出納入 `record-only` 課程（例如 `115-1_CP30210`，無 `notebook_id`）後，產出列表中會出現 `done` 紀錄並顯示「重新生成」按鈕。點擊該按鈕會送出 `POST /api/courses/{code}/jobs/regenerate`：

- **錯誤訊息**：後端直接排入 `v2` 工作並啟動 `WorkerPool` 執行生成（HTTP 200），隨後因未設定 Gemini Notebook 筆記本而在遠端生成階段失敗（或誤建遠端筆記本／拋出例外）。
- **重現步驟**：
  1. 以 `record-only` 模式登錄課程 `115-1_CP30210`。
  2. 執行 `adopt_existing_outputs("115-1_CP30210", dry_run=False)` 建立 `done` 工作。
  3. 呼叫 `POST /api/courses/115-1_CP30210/jobs/regenerate`（`lecture_no=1`, `artifact_type="study_guide"`）。
- **影響範圍**：`services/course_settings.py::CourseSettingsService.regenerate` 與 `entrypoints/static/studio-batch.js::jobRowHtml` / `jobGroupsHtml`。

## 2. 根本原因

`CourseSettingsService.regenerate` 僅驗證 `artifact_type` 與 `lecture_no` 是否合法，未檢查課程 `profile == ProfileName.RECORD_ONLY`，前端 `jobRowHtml` 也對所有 `done`/`failed` 工作無條件顯示「重新生成」與加排產出列，導致不應連線生成的 `record-only` 課程仍可建立生成任務。

## 3. 修正或規避方式

- 已於 `33e8321` 修正後端 `CourseSettingsService.regenerate` 開頭檢查 `course.profile == ProfileName.RECORD_ONLY`，若是則拋出 `ValueError`（HTTP 對應回傳 `422`）禁止排入新版本任務（`Refs: ISSUE-068`）。
- 前端 `studio-batch.js` 於 `data.profile === 'record-only'` 時停用該課程的「重新生成」按鈕（附提示文字）並隱藏加排產出列（`Refs: ISSUE-068`）。

## 4. 防回歸

- `tests/test_adopt_outputs.py::AdoptOutputsTests::test_record_only_course_refuses_regenerate_and_disables_button`

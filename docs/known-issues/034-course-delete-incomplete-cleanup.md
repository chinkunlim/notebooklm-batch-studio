# ISSUE-034：刪除課程後資料庫與前端畫面殘留舊課程狀態

- **狀態**：🔴 未解決 (Open)
- **發現日期**：2026-11-09
- **Agent**：`antigravity`
- **任務**：`TASK-014`

## 1. 現象

在「批次排程」頁面刪除課程後，雖然本機產出檔案已移至 `DATA_DIR/deleted/`，但切換到「研讀工作室」、「研讀總覽」與「弱點複習」時，仍會看到剛刪除課程的名稱、講次清單與殘留內容。若日後重新加入同課號的課程，舊的重點、AI 家教對話與進度記憶也會殘留。

- **錯誤訊息**：無拋出例外（前端狀態與後端部分資料表未同步清除）
- **重現步驟**：
  1. 在「批次排程」選擇目前唯一（或正在研讀）的課程，點擊「刪除課程」並確認。
  2. 觀察頂部課程選擇器（`#coursePick`），仍顯示已刪除課程的代碼與名稱。
  3. 切換到「研讀工作室」（課程目錄或研讀分頁）、「研讀總覽」或「弱點複習」，畫面仍保留該課程的講次、麵包屑、PDF 課件、語音摘要曲目、本講重點、工作台面板與學習數據。
- **影響範圍**：
  - 後端：`src/notebooklm_batch_studio/adapters/db/repository.py`（`CourseRepository.delete_course`）
  - 前端：`src/notebooklm_batch_studio/entrypoints/static/studio-app.js`、`studio-batch.js`、`studio-bench.js`、`studio-reader.js`、`studio-player.js`、`studio.js`、`studio-learning.js`

## 2. 根本原因

1. **前端歸零早退未重置全域狀態**：
   - `studio-app.js` 的 `initStudyPortal()` 在 `currentCoursesList.length === 0` 時僅更新 `<select id="studyCourseSelect">` 就直接 `return`，未將 `currentStudyCourse`、`activeStudyLectureNo`、`studyHistory`、`studyMistakes`、`currentQuizData`、`currentFlashcards` 等全域狀態清為空值。
   - 各頁面的繪製函式（`renderCourseDirectory`、`renderCoursePicker`、`onLectureChanged`、`loadReader`、`loadLectureAudio`、`loadTodayPanel`、`renderMemoryPanel`、`loadWeaknessNotebook`、`loadReviewCards`）在 `currentStudyCourse` 仍指向舊物件時繼續繪製舊資料，或在 `!currentStudyCourse` 時直接 `return` 而不清空既有 DOM。
   - `studio-batch.js` 的 `closeDetail()` 未重置右欄 `#activeJobs`（「進行中」列表）。
2. **後端資料庫漏刪後期新增的關聯表**：
   - `CourseRepository.delete_course()` 實作於早期，後續新增的 `KeyPointsRecord`（`key_points` 表）、`TutorMessageRecord`（`tutor_messages` 表）與 `UiPreferenceRecord`（`ui_preferences` 表中與該課號相關的 `course`、`place:<code>`、`audio:<code>:*`、`examNotice:<code>`）未納入刪除範圍。
3. **前端偏好快取未同步忘記**：
   - 刪除課程時未呼叫 `forget()` 清除前端 `mem` 與 `localStorage` 中屬於該課程的 `course`、`place:<code>`、`audio:<code>:*`、`examNotice:<code>` 鍵值。

## 3. 修正或規避方式

1. **後端（維持產出檔案移至 `DATA_DIR/deleted/` 備份）**：
   - 在 `CourseRepository.delete_course(code)` 中補齊刪除 `KeyPointsRecord`、`TutorMessageRecord`，以及 `UiPreferenceRecord` 中屬於該課程的偏好鍵（`key == f"place:{code}"`、`key == f"examNotice:{code}"`、`key.like(f"audio:{code}:%")`，以及當 `key == "course"` 且 `value == code` 時刪除）。
2. **前端**：
   - 刪除課程時清除前端對應的偏好快取（`course`、`place:<code>`、`examNotice:<code>`、`audio:<code>:*`），並重置 `#activeJobs` 為預設提示。
   - 在 `initStudyPortal()` 當 `currentCoursesList.length === 0` 時，將 `currentStudyCourse = null`、`activeStudyLectureNo = null`、`studyHistory = []`、`studyMistakes = []`，並呼叫統一的空白狀態清理流程，重置頂部課程選單、課程目錄右欄、研讀工作室（麵包屑、PDF 閱讀器、播放器停止並清空、本講重點、工作台面板）、研讀總覽與弱點複習的所有殘留 DOM。
   - 當仍有其他課程但被刪的是當前研讀課程時，自動切換至剩餘的第一門課程並完整重載。
   - 相關程式碼註解加 `Refs: ISSUE-034`。

## 4. 防回歸

- 後端單元測試（`tests/test_course_settings.py`）：驗證 `delete_course` 後，`key_points`、`tutor_messages` 與該課程的 `ui_preferences` 紀錄皆為空，且產出檔案仍移至 `DATA_DIR/deleted/`。
- 前端驗證：刪除唯一課程及刪除多門課中的當前課程後，檢查頂部課程選單、研讀總覽、研讀工作室、弱點複習與批次排程皆無殘留名稱或畫面。

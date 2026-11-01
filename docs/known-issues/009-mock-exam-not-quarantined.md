# ISSUE-009：整門課模擬考題數不足仍標成完成

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-008`

## 1. 現象

整門課模擬考最多產生 5 次仍湊不滿目標題數（預設 50）時，程式照樣把不完整的考卷存進正式產出資料夾並標成 DONE，和講次測驗的處理方式（ISSUE-002）不一致。

- **錯誤訊息**：無（靜默）
- **重現步驟**：NotebookLM 每次只回少量題目，跑 COURSE_MOCK_EXAM
- **影響範圍**：`services/artifact_runner.py` `_process_mock_exam`

## 2. 根本原因

`_process_mock_exam` 忽略 `merge_and_deduplicate_quizzes` 回傳的「是否完整」旗標，直接呼叫 `_save_quiz_files`。

## 3. 修正或規避方式

把講次測驗的隔離邏輯抽成 `_quarantine_quiz`，模擬考不完整時一樣改名 NotebookLM 上的產出、存到 `needs_review/<課程>_course_<類型>/`，並拋 `NeedsReviewError` 讓工作變成 NEEDS_REVIEW。

## 4. 防回歸

`tests/test_remaining_fixes.py`：`MockExamQuarantineTest`。

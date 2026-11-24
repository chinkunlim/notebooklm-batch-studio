# ISSUE-050：遷移到學習資料夾的課程，產出檢視與下載回 404

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-028`

## 1. 現象

課程詳情把產出列在 <study_dir>/03 Notes/NotebookLM，但 /api/artifacts/{code}/view|download 仍到 output/courses/<code> 找檔，研讀工作室的學習指南等報告顯示 404。

- **錯誤訊息**：`GET /api/artifacts/115-1/view/03_.../study_guide.md` → 404 `Requested file not found`
- **重現步驟**：開啟已遷移到 `<STUDY_ROOT_DIR>/<term>/<subject>` 的課程，在研讀工作室點學習指南、概念說明等報告。
- **影響範圍**：所有經 ADR-011 遷移的課程的報告檢視、心智圖、下載連結。

## 2. 根本原因

ADR-011 遷移後只有 course_onboarding、quiz_reader、orchestrator 改用 resolve_course_output_root，artifacts 路由漏改。

## 3. 修正或規避方式

artifacts._course_output_root 依課程 study_dir 呼叫 resolve_course_output_root。（相關程式碼註解加 `Refs: ISSUE-050`）

## 4. 防回歸

tests/test_security_hardening.py::ArtifactStudyDirTests；實機 115-1 study_guide.md 由 404 變 200。

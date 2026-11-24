# ISSUE-056：筆記生成面板的講次選單顯示 undefined、選了也不會帶入

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-029`

## 1. 現象

TASK-027 的課程自動帶入：講次下拉選單每項顯示「undefined — 檔名」、value 為空，選擇講次不會填入章節 ID、標題、PDF 路徑與 source_id；即使填入，PDF 路徑也少了 02 Handout/ 子資料夾。

- **錯誤訊息**：無（選單文字為 `undefined — Ch01-….pdf`）
- **重現步驟**：筆記頁選課程 115-1，展開講次選單。
- **影響範圍**：note-studio 生成面板的自動帶入（SPEC-013）。

## 2. 根本原因

studio-notes-gen.js 讀 l.lecture_no，但 /api/courses/{code} 的講次欄位是 no；lecture_to_dict 也沒有輸出 relative_path / category，前端只能用 source_dir/檔名拼路徑。

## 3. 修正或規避方式

前端改讀 no、標題優先用 topic；lecture_to_dict 補 category 與 relative_path。實機 115-1 第 3 講帶入 ch03、標題、source_id 與 …/02 Handout/Ch03-….pdf，且通過 NotePathResolver 檢查。（相關程式碼註解加 `Refs: ISSUE-056`）

## 4. 防回歸

tests/test_note_pipeline_phase2.py::test_course_detail_lecture_fields_used_by_notes_form。

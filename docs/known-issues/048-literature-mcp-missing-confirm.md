# ISSUE-048：文獻 MCP 工具會修改資料卻沒有 confirm 參數

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-028`

## 1. 現象

add/process/refresh/import_to_course/unarchive_literature、sync_literature_notebook、generate_literature_review、save_qa_note 會新增資料、搬檔、上傳或花額度，違反核心規則 13；這些工具同時回傳不可信的文獻文字，提示注入可連鎖呼叫。

- **錯誤訊息**：無（工具直接執行）
- **重現步驟**：以 MCP 呼叫 `sync_literature_notebook()` 或 `add_literature(text=...)`，未帶 confirm 即上傳／新增。
- **影響範圍**：所有連到 MCP 的 Agent；`query_literature_notebook` 回傳的文獻文字若含注入指令，可誘導 Agent 連鎖呼叫上傳、搬檔或花額度。

## 2. 根本原因

literature-fetch 與 QA 筆記整合時沿用原專案的工具簽章，沒套用本專案的 confirm 規則。

## 3. 修正或規避方式

上述 8 個工具加 confirm=False 預設，未確認時統一回傳 `{"confirmed": false, "warning": "..."}`；參數過多者改用 LiteratureTarget / QANoteInput 物件；文獻 Notebook 工具拆到 mcp_literature_notebook.py。（相關程式碼註解加 `Refs: ISSUE-048`）

## 4. 防回歸

tests/test_security_hardening.py::test_mutating_literature_tools_require_confirm 逐一驗證文獻、QA 筆記與筆記管線 MCP 工具。

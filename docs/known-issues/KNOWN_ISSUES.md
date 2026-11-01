# 已知問題 (Known Issues)

記錄「踩過的坑」：值得記住的 bug、外部服務的怪行為、環境問題，以及它們的根本原因與修正方式。
除錯時先查這裡：`grep -rn "關鍵字" docs/known-issues .agents/conversations`（後者只在本機）。

- 新增：`python3 .agents/skills/adr-issue-tracker/scripts/tracker_cli.py --add-issue <slug> --title "標題" --summary "錯誤訊息" --agent <名字>`
- 格式：[`_TEMPLATE.md`](_TEMPLATE.md)；在修正的程式碼註解加 `Refs: ISSUE-NNN`，並寫防回歸測試。
- 狀態：🔴 未解決 (open) → 🟡 已規避 (mitigated) → 🟢 已根治 (resolved)

> 命名規則：`_TEMPLATE.md` 是新增紀錄時要照著寫的範本；紀錄檔命名為 `NNN-<slug>.md`。整個專案只有根目錄一份 `README.md`。

## 總表

| ISSUE | 狀態 | 標題 | 現象 | 程式與測試 |
|---|---|---|---|---|
| [ISSUE-001](001-ollama-refine-noop.md) | 🟢 已根治 (Resolved) | Ollama 提示詞改寫實際上沒有呼叫 Ollama | refine_course_prompts_with_ollama 回報成功改寫 N 筆，但 prompt 內容其實沒變 | `services/orchestrator.py`, `entrypoints/api.py`, `entrypoints/mcp_server.py` |
| [ISSUE-002](002-quiz-needs-review-status.md) | 🟢 已根治 (Resolved) | 題數不足的測驗被標成 DONE 而非 NEEDS_REVIEW | 湊不滿 30 題的測驗已隔離到 needs_review/，但工作狀態是 DONE，總覽報告看不到需審查警告 | `services/artifact_runner.py`, `services/worker_pool.py`, `adapters/db/repository.py` |

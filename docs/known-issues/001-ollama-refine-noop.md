# ISSUE-001：Ollama 提示詞改寫實際上沒有呼叫 Ollama

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-007`

## 1. 現象

refine_course_prompts_with_ollama 回報成功改寫 N 筆，但 prompt 內容其實沒變

- **錯誤訊息**：無（靜默失敗，API 回傳 `{"updated_prompts": N}`）
- **重現步驟**：網頁或 MCP 呼叫 `refine_prompts_with_ollama`，再看工作的 `custom_prompt`，內容仍是母版 prompt
- **影響範圍**：`POST /api/courses/{code}/refine_prompts`、MCP `refine_prompts_with_ollama`

## 2. 根本原因

`BatchStudioService.refine_course_prompts_with_ollama` 建立 `PromptGenerator()` 時沒有傳入 Ollama client，
`generate_refined_prompt` 因此一律直接回傳母版 prompt。函式只要 `update_job_prompt` 成功就計數，所以仍回報「已改寫」。
另外 `.env` 的 `OLLAMA_MODEL` 從未被 config 讀取，`OllamaClient` 一律使用寫死的 `gemma4:latest`。
服務層依分層規則不能 import adapter，但入口層也沒有注入 client，這個缺口沒有測試覆蓋。

## 3. 修正或規避方式

- `BatchStudioService` 新增 `ollama_client` 參數，由 `entrypoints/api.py` 與 `entrypoints/mcp_server.py` 注入 `OllamaClient`。
- 沒有 client 或 Ollama 連不上時拋出 `OllamaUnavailableError`（HTTP 回 503，MCP 回 error JSON），不再假裝成功。
- 只改寫未完成的工作（跳過 DONE、RUNNING），且只計算內容確實改變的 prompt。
- `AppConfig.ollama_model` 讀取 `OLLAMA_MODEL`，`OllamaClient` 預設使用它。

## 4. 防回歸

`tests/test_needs_review_and_ollama.py`：`OllamaRefineTest.test_refine_updates_unfinished_jobs_with_ollama_output`、
`OllamaRefineTest.test_refine_raises_when_ollama_missing_or_down`。

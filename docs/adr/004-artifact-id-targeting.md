# ADR-004：以 generate 回傳的 artifact_id 精準下載與改名，取代取最新一份

- **狀態**：Accepted <!-- Proposed | Accepted | Superseded by ADR-NNN -->
- **日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-008`

## 1. 背景與問題

多個 worker 並行時，依建立時間取最新產出會拿到別講次的產出

notebooklm-py 0.8.5 的 `generate_*` 回傳 `GenerationStatus`，其 `task_id` 就是產出完成後的 `artifact_id`。
舊程式不保留這個 id：下載時呼叫 `download_*` 不帶 `artifact_id`（函式庫取該類型最新完成的一份），
改名時用 `find_latest_artifact` 取整本筆記本最新的一份（還忽略類型篩選）。WorkerPool 預設 2 個 worker 並行，
第 1 講與第 2 講可能同時產生測驗，違反 PROJECT_RULES「每份 PDF 單獨生成」。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. generate 等待完成並回傳 artifact_id，download / rename 一律帶這個 id | 精準、無競態、不需額外 list 呼叫 | Protocol 介面要改，測試 mock 要跟著改 |
| B. 維持「取最新一份」，改成 concurrency=1 | 改動小 | 速度減半，且手動在 NotebookLM 產生的東西仍會被誤抓 |
| C. 產生後 list 全部產出，依標題比對 | 不改 generate 回傳 | 標題由 NotebookLM 生成、不可靠；多一次 RPC |

## 3. 決策與理由

選 A。`task_id == artifact_id` 是函式庫明文保證（`_types/artifacts.py` 的 `GenerationStatus` 註解），
直接沿用最穩定。所有 `generate_*` 在 adapter 內呼叫 `finish_generation`（`adapters/notebooklm/generation.py`）：
檢查狀態 → `wait_for_completion` → 再檢查 → 回傳 id。心智圖例外：它是同步產生並存成 note，回傳 `note_id`，
下載時帶 note id，不做 artifact 改名。

## 4. 影響與代價

- `NotebookLMClientProtocol`：generate 回傳「已完成的 artifact id」；移除 `find_latest_artifact` 與 `wait_for_completion`；
  新增 `get_source_limit`、`get_quota_status`；`generate_quiz` 加 `difficulty`，`generate_audio` / `generate_mind_map` 加 `language`。
- `ArtifactRunner` 各 `_process_*` 回傳（路徑, artifact ids），`rename_after_generation` 只改這些 id。
- 之後新增產出類型時：generate 必須經 `finish_generation`，download 必須帶 id。
- 相關問題：ISSUE-003（語言）、ISSUE-004（錯拿產出）、ISSUE-005（配額狀態）。

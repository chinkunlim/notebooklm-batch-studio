# ISSUE-011：心智圖在 NotebookLM 上沒有改名

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

完整跑完一門課後，其他產出都改成 `[Ch01] Quiz 1 - Fundamentals` 這類標題，只有 7 份心智圖維持 NotebookLM 自動取的名字。

- **錯誤訊息**：無（靜默）
- **重現步驟**：跑任一含 MIND_MAP / COURSE_MIND_MAP 的 profile，到 NotebookLM 看心智圖名稱
- **影響範圍**：`services/artifact_runner.py` `_process_mindmap`、`rename_after_generation`

## 2. 根本原因

心智圖存成 NotebookLM 的 note，不是 studio artifact，`artifacts.rename` 改不到它。程式因此刻意讓 `_process_mindmap`
回傳空的 id 清單，等於跳過改名；而 notebooklm-py 其實有 `client.mind_maps.rename(..., kind=NOTE_BACKED)`。

## 3. 修正或規避方式

- adapter 新增 `rename_mind_map`，走 `client.mind_maps.rename`。
- `_process_mindmap` 回傳 note id，`rename_after_generation` 對心智圖類型改呼叫 `rename_mind_map`。
- 工作完成後把 id 存進 `artifact_ids`（ADR-005），之後可以補改名。
- 已產生的 7 份用一次性腳本依 log 中「Mind map saved as note」與完成紀錄對應後補改名。

## 4. 防回歸

`tests/test_versions_and_options.py`：`test_mind_map_is_renamed_through_mind_map_api`、`test_execute_records_artifact_ids`。

# ISSUE-017：測驗 prompt 只要求 10 題，且寫死研究法領域

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

- 每份講次測驗要湊滿 30 題，常需要生成 2～3 批；NotebookLM 上出現多份同名的「Quiz 2 - Application」，也多花額度。
- 測驗與共用 prompt 寫死「研究假設、效度威脅、心理學與統計學名詞」，換成其他科目會出不相干的題型；基礎測驗也被要求「研究所水準」。

- **錯誤訊息**：無
- **重現步驟**：看 NotebookLM Studio 的測驗清單；或檢查 `PromptGenerator` 對 QUIZ_1 的輸出
- **影響範圍**：`services/prompt_generator.py`、`services/artifact_runner.py` `rename_after_generation`

## 2. 根本原因

prompt 是以第一門測試課程（心理學研究法）撰寫的範本，題數也沿用早期「每批 10 題」的設計，沒有跟著 30 題的需求更新。

## 3. 修正或規避方式

- 測驗 1/2/3、學術精研、概念刷題一律要求 30 題，內容改為不限科目的描述；共用前綴不再強制研究所難度。
- 一份測驗若仍分多批，NotebookLM 標題加「(1/3)、(2/3)…」。

## 4. 防回歸

`tests/test_domain_and_queue.py`：`test_prompt_generator_master_blueprint`；`tests/test_selection_and_folders.py`：`test_batches_are_numbered`。

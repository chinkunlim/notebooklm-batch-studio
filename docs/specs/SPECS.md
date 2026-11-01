# 需求與規格 (Specs)

一個功能一份規格，先寫規格再實作；實作時在任務卡與 commit 中引用規格檔名。

- 新增：複製 [`_TEMPLATE.md`](_TEMPLATE.md) 為 `NNN-<slug>.md`（例如 `001-login-api.md`），並在下表加一列。

> 命名規則：`_TEMPLATE.md` 是新增紀錄時要照著寫的範本；紀錄檔命名為 `NNN-<slug>.md`。整個專案只有根目錄一份 `README.md`。

## 規格清單

| 規格 | 狀態 | 說明 | 實作對應 |
|---|---|---|---|
| [001-batch-generation](001-batch-generation.md) | Implemented | 資料夾 → notebook、每份 PDF 複習包、產出組合、命名、佇列與每日上限 | TASK-002, TASK-004 |
| [002-export-downloads](002-export-downloads.md) | Implemented | 下載與轉檔（quiz / mind map / flashcards / pdf）＋技術驗證 | TASK-001, TASK-003 |
| [003-web-and-ai-tools](003-web-and-ai-tools.md) | Implemented | 本機網頁、OpenAPI（Open WebUI）、MCP 工具 | TASK-005 |
| [004-phase2-self-test](004-phase2-self-test.md) | Implemented | 第二階段：學生研讀工作台、錯題本、3D卡牌、語音導讀與 Anki 間隔重複匯出 | TASK-007, ADR-003 |

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
| [005-generation-options-and-versions](005-generation-options-and-versions.md) | Implemented | 產出參數設定、重新生成版本、命名說明與網頁進度 | TASK-009, ADR-005 |
| [006-per-artifact-settings](006-per-artifact-settings.md) | Implemented | 每一項產出各自的生成設定（題型、題量、難度…），三層設定合併 | TASK-009, ADR-005 |
| [007-student-experience](007-student-experience.md) | Implemented | 學生學習體驗：今天、交卷回饋、間隔複習、模擬考、解釋、介面 | TASK-009 |
| [008-learning-aids](008-learning-aids.md) | Implemented | 學習輔助：課件重點標示、遺忘曲線記憶強度、信心評分、混合複習、家教、番茄鐘 | TASK-009, ADR-006 |
| [009-study-studio-ui-redesign](009-study-studio-ui-redesign.md) | Implemented | 研讀工作室與學生工作台介面重構（v05）：側欄四頁、真實音檔唱盤與迷你播放器、免分頁工作台、配色與自訂、全設備 RWD | TASK-011, ADR-007, ADR-008 |
| [010-user-end-to-end-workflow](010-user-end-to-end-workflow.md) | Approved | 使用者端到端完整工作流程規格書：從建立課程、設定、排程產出到研讀與下載之各步驟細緻操作與判定流程 | TASK-010 ~ TASK-017 |
| [011-notebook-qa-notes-and-tag-system](011-notebook-qa-notes-and-tag-system.md) | Implemented | Gemini Notebook 探索提問、問答筆記庫與階層標籤系統（隨身抽屜、大頁面、格式化總結、來源回灌與測驗整合） | TASK-024, ADR-010 |
| [012-literature-fetch-and-study-hierarchy](012-literature-fetch-and-study-hierarchy.md) | Implemented | 整合 literature-fetch 文獻下載與統一學習目錄結構（`<學年>-<學期>/<科目>/<分類>`） | TASK-025, ADR-011 |
| [013-note-studio-markdown-notes](013-note-studio-markdown-notes.md) | Implemented | note-studio 模組化學習筆記：7 模組提示詞、雙後端生成、單章 `.md` 縫合、推回來源與舊筆記匯入 | TASK-026, TASK-027, ADR-012 |

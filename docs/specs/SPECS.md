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
| [010-user-end-to-end-workflow](010-user-end-to-end-workflow.md) | Implemented | 使用者端到端完整工作流程規格書：從建立課程、設定、排程產出到研讀與下載之各步驟細緻操作與判定流程 | TASK-010 ~ TASK-017 |
| [011-notebook-qa-notes-and-tag-system](011-notebook-qa-notes-and-tag-system.md) | Implemented | Gemini Notebook 探索提問、問答筆記庫與階層標籤系統（隨身抽屜、大頁面、格式化總結、來源回灌與測驗整合） | TASK-024, ADR-010 |
| [012-literature-fetch-and-study-hierarchy](012-literature-fetch-and-study-hierarchy.md) | Implemented | 整合 literature-fetch 文獻下載與統一學習目錄結構（`<學年>-<學期>/<科目>/<分類>`） | TASK-025, ADR-011 |
| [013-note-studio-markdown-notes](013-note-studio-markdown-notes.md) | Implemented | note-studio 模組化學習筆記：7 模組提示詞、雙後端生成、單章 `.md` 縫合、推回來源與舊筆記匯入 | TASK-026, TASK-027, ADR-012 |
| [014-study-library-and-learning-record](014-study-library-and-learning-record.md) | Implemented | 學習資料庫統一與完整學習紀錄：學期＋課號身分、複數分類與別名、scratch 歸檔、課程封存與安全改碼、跨學期紀錄匯出 | TASK-035, ADR-014 |
| [015-adopt-existing-outputs](015-adopt-existing-outputs.md) | Implemented | 從既有 `03 Notes/NotebookLM/` 產出檔建立 `done` 產出紀錄（重用既有命名規則、預設 dry-run、三入口、不動檔不連網） | SPEC-014 Q6 |
| [016-study-library-web-management](016-study-library-web-management.md) | Implemented | 學習資料夾網頁管理：學習紀錄頁登錄舊課（record-only＋封存）、非標準資料夾手動登錄、scratch 歸檔／撤銷歸檔、修改課程顯示名稱（HTTP／MCP／網頁） | TASK-039, TASK-038 |
| [017-notes-files-notifications-versions-backups](017-notes-files-notifications-versions-backups.md) | Implemented | NoteStudio 其他筆記檔瀏覽、課程全部產出完成 macOS 通知、`_vN` 多版本產出納管、資料庫備份整理（移到 deleted/，不刪除） | TASK-038 |
| [018-textbook-split-and-lecture-source](018-textbook-split-and-lecture-source.md) | Implemented | 課本依書籤切割成章節 PDF（pypdf，移植 literature-parser）、`02 Handouts` 為空時以 `.textbook.json` 標記的章節資料夾為講次、把誤放講義資料夾的章節搬到 `01 Materials/<課本>/`（保留講次編號與來源） | TASK-037 |
| [019-web-gap-fill-profile-resume-retention](019-web-gap-fill-profile-resume-retention.md) | Implemented | 網頁補齊：課程「變更產出模式…」、筆記生成「繼續」、Gemini 憑證保留天數；無效產出模式回 422 | 網頁整合盤點 |
| [020-textbook-detect-note-schedule-quota-resume](020-textbook-detect-note-schedule-quota-resume.md) | Implemented | 課本放進 01 Materials 自動偵測並提示切割、Gemini 筆記背景排程（允許一次後依序生成）、Gemini 額度用完記下重置時間到點續跑、Gemini Notebook 佇列顯示預計繼續時間 | 使用者 2026-11-25 定案 |
| [021-learning-site-artifacts](021-learning-site-artifacts.md) | Implemented | 學習網頁產出：每講與整本書經 Gemini Notebook 對話「make me a site」產生、從 Studio（類型 10、text/html）下載、以沙箱 CSP 開啟並把作答進度存回研讀工作室（真實資料驗收待使用者同意） | TASK-040、ADR-016 |
| [022-real-chrome-sign-in-and-library-browser](022-real-chrome-sign-in-and-library-browser.md) | Draft | Gemini Notebook 登入與文獻瀏覽器改用真的 Chrome（獨立資料夾＋CDP），不繞過機器人檢查 | TASK-042、ISSUE-043 |
| [023-retire-migrate-study-layout](023-retire-migrate-study-layout.md) | Draft | 停用舊的 migrate-study-layout（HTTP 回 410、移除 MCP 工具），改用 consolidate；待使用者決定 D5 | TASK-043 |
| [024-link-record-only-course-to-existing-notebook](024-link-record-only-course-to-existing-notebook.md) | Draft | 只記錄的課程連結既有 Gemini Notebook（依檔名對來源、不重新上傳），以產生新產出；使用者決定暫停 | TASK-041 |
| [025-robustness-backlog](025-robustness-backlog.md) | Draft | 穩定性待辦：筆記排程跨程序檔案鎖、notebooklm-py 升級把關、多本課本選資料夾、講次來源切換防護與「both」 | 盤點 2026-11-25 |
| [026-pending-acceptance-and-manual-tests](026-pending-acceptance-and-manual-tests.md) | Draft | 尚待驗收項目與使用者實機測試步驟（整本書學習網頁、課本切割、額度續跑、完成通知、TASK-036） | TASK-036、TASK-040 |

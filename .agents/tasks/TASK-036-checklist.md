# TASK-036 實機驗收與整理清單 — User manual verification and housekeeping checklist

- **狀態**：`open`
- **負責**：使用者本人（需要本人帳號、手機或外部 App）；Agent 只協助準備與核對證據
- **建立日期**：`2026-11-25`
- **來源**：Task 17 回報的 16 項待實機清單＋2026-11-25 收尾盤點

## 1. 盡快處理（幾分鐘）

1. [ ] **關閉或封存舊對話**：11/24 開的兩個 Claude Code 對話，其 `notebooklm-batch-studio` MCP 伺服器仍是 ISSUE-069 修正前的舊程式（`/mcp` 無法重新連線）。之後只在新對話使用 MCP 工具；舊對話裡不要實際執行 `migrate_study_layout`。
2. [ ] **用平常方式啟動網頁伺服器**：2026-11-25 12:2x 由 Claude 桌面 App 的瀏覽器面板啟動（`uv run notebooklm-batch-studio web`），結束該對話可能會停。之後用「Gemini Notebook 學習工作室」App 或 `uv run notebooklm-batch-studio-web` 開啟。
3. [ ] **（可選）刪除空的 `DATA_DIR/output/`**：0 個檔案、資料庫沒有指向它；`doctor --fix`／`install.sh` 會重建空資料夾，可忽略。
4. [ ] **（可選）整理 `DATA_DIR/backups/`**：2026-11-25 產生 `db-20261125-082418`、`-095810`、`-115355`、`-122559` 等多份；確認資料無誤後可只留最新一兩份（見 TASK-038 保留策略）。

## 2. 實機確認（依花費時間由少到多）

| # | 項目 | 怎麼測 | 預期結果 | 狀態 |
|---|---|---|---|---|
| 1 | SPEC-015 測驗作答 | 網頁 → 研讀工作室 → 心理學研究法第 1 講「測驗 1・基礎」真的交一次卷 | `quiz_attempts` 新增一筆；學習紀錄的測驗次數／學習天數更新；答錯題進「弱點複習」；仍無法按「重新生成」 | ⬜ |
| 2 | SPEC-009 手機版面 | iPhone 開網頁（或瀏覽器縮到 ≤ 680px）逐頁檢查 | 單欄重排、無橫向捲動、黑膠唱盤等比縮放 | ⬜ |
| 3 | SPEC-009 工作台工具 | 研讀工作室逐一點 11 張工具卡 | 面板展開、高度對齊、不跑版 | ⬜ |
| 4 | SPEC-002 匯入外部 App | `anki.csv` 匯入 Anki；`mindmap.opml` 匯入 XMind | 正反面與標籤正確；多層心智圖、中文無亂碼 | ⬜ |
| 5 | SPEC-011 Obsidian 標籤 | 用 Obsidian 開 `03 Notes/QA_Notes/` | `#課程/…`、`#掌握度/…` 顯示為標籤樹 | ⬜ |
| 6 | SPEC-011 提問抽屜 | `Cmd+J` 提問 → 存成問答筆記 → 展開大頁 | 抽屜開合順暢、筆記可篩選 | ⬜ |
| 7 | SPEC-003 Open WebUI | 掛 `http://127.0.0.1:8768/openapi.json`，問「生涯諮商與實務做到哪了」 | 模型呼叫課程 API 並正確回報完成度 | ⬜ |
| 8 | 核心規則 14 更新流程 | 關掉伺服器後執行 `./scripts/update.sh --no-pull` | 依序：同步依賴 → 確認伺服器已停 → 備份到 `backups/db-<時間>/` → `alembic upgrade head` → `init-data`，全部成功 | ⬜ |
| 9 | SPEC-014 watch 監看 | `uv run notebooklm-batch-studio watch`，分別放 PDF 到 `02 Handouts/`、`01 Materials/`、`04 Homework/` | 只有 `02 Handouts/` 觸發排程 | ⬜ |
| 10 | SPEC-014 scratch 歸檔 | 用 MCP `file_item` / `unfile_item`（網頁尚無入口，見 TASK-039） | 不覆寫同名檔；撤銷退回 `scratch/unarchived/<課程代碼>/` | ⬜ |
| 11 | SPEC-014 登入狀態 | 「設計與自訂」查看三組登入卡片 | 正確顯示就緒／未登入／已過期，不外洩 cookie | ⬜ |
| 12 | SPEC-001 多資料夾上傳 ⚠️耗額度 | 加 2 門課並開始生成 | 2 本筆記本、PDF 全部上傳、重掃不重複 | ⬜ |
| 13 | SPEC-002 / 005 真實產出與 v2 ⚠️耗額度 | 一講跑完整產出，再按一次「重新生成」 | 8 件產出檔名正確；保留 v1 並新增 `_v2` 與裝置版圖檔 | ⬜ |
| 14 | SPEC-003 網頁端對端 | 網頁加課 → 預覽 → 確認 → 等佇列 → 下載 | 預覽估算正確、下載與檢視器可開 | ⬜ |
| 15 | SPEC-010 八階段走一輪 | 依 SPEC-010 從啟動到弱點複習 | 全程無卡死、無 4xx/5xx | ⬜ |
| 16 | SPEC-014 登錄舊學期課程 | 從雲端備份複製 113-1～114-2 到 `study/<學期>/`，用 MCP `scan_study_library` → `register_past_courses(confirm=True)`（網頁尚無入口，見 TASK-039）；有舊 NotebookLM 產出再用「從既有檔案建立產出紀錄」 | 以 record-only＋archived 登錄、佇列 0 筆新工作；學習紀錄依學期列出；匯出 MD／PDF 可開 | ⬜ |
| 17 | 示範頁 | 直接開 `docs/demo/index.html` | 離線可用、學期分組與 record-only 封存課正確 | ⬜ |

## 3. 不可修改之使用者決定

- 只封存、不刪除；課程要先封存才能刪除（Google Classroom 模式）。
- 資料只放 `projects-data/notebooklm-batch-studio/`；iCloud 只當備份，程式不讀寫 iCloud。
- 課程資料夾採校方命名 `study/<學期>/<CODE__NUM-課名>/`，五個分類 `01 Materials`…`05 Assignments`。
- `02 Handouts` 只放老師講義；完整課本放 `01 Materials/`，切割後放 `01 Materials/<課本名>/`（TASK-037）。

## 4. 實證回報格式

- **已證實**：附實機 log、截圖或 DB 查詢結果
- **推測**：尚未實測（不可寫成已完成）
- **失敗**：現象＋完整錯誤訊息

# ADR-018：停用 migrate-study-layout，舊資料整併一律用 consolidate

- **狀態**：Accepted <!-- Proposed | Accepted | Superseded by ADR-NNN -->
- **日期**：2026-11-26
- **Agent**：`claude-code`
- **任務**：`TASK-043`

## 1. 背景與問題

有兩個工具都在搬課程資料夾：舊的 migrate-study-layout（只有 HTTP POST /api/courses/migrate-study-layout 與 MCP migrate_study_layout）與新的 consolidate（CLI，先預覽、--apply 才套用、伺服器與佇列停止才可執行，ADR-015）。舊工具的 HTTP 預設 dry_run=False（一呼叫就搬），曾差點把兩門課搬離學校命名的資料夾（ISSUE-069）；使用者三門課都已在 study/，執行結果全是 already_migrated，已無用途，留著只會讓 AI 工具誤叫。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. 保留兩個工具 | 不用改 | 舊工具預設會直接搬檔、曾出事（ISSUE-069）；AI 工具可能誤叫；兩套搬檔邏輯要維護 |
| B. 只移除 MCP 工具、HTTP 照舊 | 改動小 | Open WebUI 仍看得到並可呼叫會搬檔的路由 |
| C. HTTP 回 410＋移除 MCP 工具＋刪除程式（採用） | 誰呼叫都得到明確指引；只剩 consolidate 一套搬檔邏輯 | 舊腳本要改用 CLI |

## 3. 決策與理由

使用者 2026-11-26 同意停用（D5）。HTTP 路由保留但一律回 410 Gone（OpenAPI 標 deprecated），說明改用 consolidate，不讀請求內容、不碰任何檔案；移除 MCP 工具；刪除 services/study_migration.py 與 adapters/db/study_migration_repo.py（只服務這個工具）。consolidate 已涵蓋平鋪 input/courses → study/（tests/test_legacy_consolidation.py）。

## 4. 影響與代價

舊腳本或 AI 工具呼叫會得到明確指引而不是搬檔。Claude Code／Antigravity 的 MCP 伺服器重新載入後工具清單不再有 migrate_study_layout。測試：tests/test_migrate_study_layout_retired.py。

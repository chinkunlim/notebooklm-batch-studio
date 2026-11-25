# SPEC-023：停用舊的「遷移學習資料夾」（migrate-study-layout），改用 consolidate

- **狀態**：Implemented（使用者 2026-11-26 同意停用，ADR-018）<!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-25
- **相關任務 / ADR**：TASK-043（決策 D5）／ISSUE-069／ADR-015（整併只在伺服器停止時套用）／SPEC-012

## 1. 目標

有兩個工具都在搬課程資料夾：

| | 舊的 `migrate-study-layout` | 新的 `consolidate` |
|---|---|---|
| 程式 | `services/study_migration.py::migrate_courses_to_study_hierarchy` | `services/legacy_consolidation.py` |
| 入口 | HTTP `POST /api/courses/migrate-study-layout`（`entrypoints/http/literature_files.py:107`）、MCP `migrate_study_layout`（`entrypoints/mcp_literature.py:362`）；網頁沒有按鈕、CLI 也沒有 | CLI `uv run notebooklm-batch-studio consolidate`（預覽）／`--apply` |
| 範圍 | 早期平鋪的 `input/courses`、`output/courses` → `study/<學期>/<課程>/<分類>` | 所有舊位置（`input/courses`、`output/courses`、`midterm-submission`、舊筆記工具資料）→ `study/`，產出報告 |
| 安全 | 曾差點把兩門課搬離學校命名資料夾（ISSUE-069，已修） | 伺服器與佇列都停止才可套用（ADR-015） |

使用者的三門課都已在 `study/`，舊工具執行結果全部是 `already_migrated`，已無用途；留著只會讓 AI 工具（Claude、Antigravity、Open WebUI）有機會誤叫。成功的樣子：AI 工具看不到 `migrate_study_layout`，呼叫舊 HTTP 路由時得到清楚的指引改用 `consolidate`。

## 2. 使用情境

- AI 工具或舊腳本呼叫 `POST /api/courses/migrate-study-layout` → 收到 410 與說明，不搬任何東西。
- 使用者要整理舊資料 → 依說明執行 `consolidate`（先預覽，再 `--apply`）。

## 3. 需求

- **必須 (Must)**：
  1. HTTP `POST /api/courses/migrate-study-layout` 改回 **410 Gone**，`detail` 說明「此功能已停用，請改用 `uv run notebooklm-batch-studio consolidate`（先預覽）」；OpenAPI 標記 `deprecated=True`，請求內容不再解析，不呼叫任何服務。
  2. 移除 MCP 工具 `migrate_study_layout`（`_register_migrate_tool` 與註冊呼叫）。
  3. 刪除 `migrate_courses_to_study_hierarchy` 與只服務它的輔助函式（實作：整個 `services/study_migration.py` 與 `adapters/db/study_migration_repo.py` 都只服務它，一併刪除）；`consolidate` 有用到的共用函式保留（實作前先用 grep 確認呼叫者）。
  4. 測試：移除舊工具的測試（`tests/test_literature_and_hierarchy.py` 中 migrate 相關的兩個），新增 410 路由測試與「MCP 工具清單不含 `migrate_study_layout`」測試；確認 `consolidate` 已有對應覆蓋（平鋪 `input/courses` → `study/` 的案例），沒有就補。
  5. 文件：README 第 21 行移除 `migrate-study-layout`；SPEC-003、SPEC-012、SPEC-019 加註「已由 SPEC-023 停用」；寫 ADR（停用原因、替代方案）。
- **可選 (Nice to have)**：無。
- **不做 (Out of scope)**：改動 `consolidate` 的行為；搬動任何真實資料。

## 4. 介面 / API

`POST /api/courses/migrate-study-layout` → `410`：

```json
{"detail": "migrate-study-layout 已停用，請改用 `uv run notebooklm-batch-studio consolidate`（先預覽，確認後加 --apply）"}
```

## 5. 驗收標準

- [x] Given 任何請求內容，When 呼叫 `POST /api/courses/migrate-study-layout`，Then 回 410 且檔案系統與資料庫都沒有變動。
- [x] Given MCP 伺服器啟動，Then 工具清單沒有 `migrate_study_layout`。
- [x] Given 平鋪的舊 `input/courses`，When 執行 `consolidate`（預覽），Then 計畫包含搬到 `study/<學期>/<課程>/` 的項目（既有或新增測試）。
- [x] `grep -rn migrate_courses_to_study_hierarchy src tests` 無結果；`agentctl check` 0 警告；ADR 已寫。
- [ ] 重新載入 Claude Code 與 Antigravity 的 MCP 伺服器後，工具清單不再出現舊工具。

## 6. 未決問題

- ~~使用者是否同意停用（D5）~~：2026-11-26 同意。實作時另發現舊 HTTP 路由預設 `dry_run=False`（一呼叫就搬），停用更有必要。
- 重新載入 Claude Code／Antigravity 的 MCP 伺服器後確認工具清單（使用者端）。

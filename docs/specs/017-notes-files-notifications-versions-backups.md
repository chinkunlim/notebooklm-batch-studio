# SPEC-017：筆記資料夾其他檔案、完成通知、多版本產出納管、資料庫備份整理

- **狀態**：Implemented <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-25
- **相關任務 / ADR**：TASK-038 (2)–(5)、SPEC-001、SPEC-013、SPEC-015

## 1. 目標

收齊 TASK-038 剩下的四個小功能：

1. 網頁與 MCP 能瀏覽 `03 Notes/NoteStudio/` 裡章節筆記以外的檔案（`00_總覽與跨章整合筆記.md`、`學習筆記/PDF/*.pdf`、`章節/**/目前/*.md`）。
2. 一門課的所有產出跑完時，macOS 跳出通知（SPEC-001 原本就有的需求）。
3. 「從既有檔案建立產出紀錄」也能納管 `_v2`、`_v3` 等重新生成的版本。
4. 整理 `DATA_DIR/backups/` 的資料庫備份：只保留最新 N 份，舊的**移到** `DATA_DIR/deleted/backups/`（只封存、不刪除）。

## 2. 使用情境

- **情境 A**：在筆記面板看到「其他筆記檔案」清單，點 `.md` 在預覽框顯示內容，點 `.pdf` 在新分頁開啟。
- **情境 B**：佇列跑完一門課的最後一項產出，macOS 通知「課程 115-1_CP31000 全部產出完成（94 項）」。
- **情境 C**：`03 Notes/NotebookLM/01_x/` 同時有 `infographic.png` 與 `infographic_v2.png`，納管後建立 v1 與 v2 兩筆 done 工作。
- **情境 D**：在「設計與自訂 → 資料庫備份」看到共 6 份備份，按「整理舊備份」先預覽「將移走 1 份」，確認後移到 `deleted/backups/`。

## 3. 需求

- **必須 (Must)**：
  1. **筆記檔案**：`list_note_files(notes_dir)` 遞迴列出 `.md`／`.pdf`（排除隱藏檔、symlink、`版本/`、`學習筆記/PDF/layout/`、`手動生成提示詞/`），每項含 `relative_path`、`kind`、`size`、`is_chapter`；`read_note_file(notes_dir, relative_path)` 只能讀 `notes_dir` 內的檔案（防目錄穿越），`.md` 回內容，`.pdf` 回路徑。HTTP `GET /api/notes/files/{course_key}`、`GET /api/notes/file/{course_key}?path=`（`.md` 回 JSON、`.pdf` 回檔案）；MCP `notes_list_files`、`notes_read_file`（唯讀，不需 confirm）；網頁筆記面板「其他筆記檔案」。
  2. **完成通知**：`WorkerPool(on_course_complete=...)`；工作成功後若該課程已無 `pending`／`running`／`quota_wait`，呼叫一次回呼並傳入各狀態數量；回呼出錯只記 log。設定 `NOTIFY_ON_COMPLETE`（預設 `true`），只在 macOS 用 `osascript` 顯示，其他平台只記 log。網頁服務與 CLI `batch` 都接上。
  3. **多版本納管**：檔名中的 `_vN`（N ≥ 2，位於副檔名或下一個 `_` 之前，與 `domain/naming.versioned_name` 相反）視為版本 N；去掉 `_vN` 後重用既有對應規則，建立 `version=N` 的 done 工作；既有判斷改為以（講次, 類型, 版本）判斷是否已存在。
  4. **備份整理**：`list_backups(config)` 回傳 `DATA_DIR/backups/db-*` 由新到舊（名稱、大小、時間）；`prune_backups(config, keep=5, dry_run=True)` 預覽或把較舊的移到 `DATA_DIR/deleted/backups/<名稱>`（同名加後綴，不覆寫），`keep` 至少 1。HTTP `GET /api/system/backups`、`POST /api/system/backups/prune {keep, dry_run}`；MCP `list_backups`、`prune_backups(keep, dry_run=True, confirm=False)`；網頁「設計與自訂 → 資料庫備份」卡片。
- **不做 (Out of scope)**：永久刪除備份（清空 `deleted/` 由使用者自行決定）；Windows／Linux 桌面通知。

## 4. 介面 / API

見第 3 節。所有會移動檔案的操作預設 `dry_run=True`。

## 5. 驗收標準

- [x] **場景 17a**：巢狀筆記結構列出總覽、PDF、`目前/` 草稿，排除 `版本/` 與 `layout/`；讀 `.md` 回內容、讀 `../` 回 400。（`tests/test_spec017_small_features.py::test_note_files_list_read_http_mcp_and_web`）
- [x] **場景 17b**：最後一項工作完成才呼叫一次回呼，仍有 pending 時不呼叫，回呼例外不影響佇列；設定關閉時不建立回呼。（`test_course_complete_hook_fires_once_when_course_finishes`）
- [x] **場景 17c**：`infographic.png`＋`infographic_v2.png`＋`quiz_1_v2_quiz.json` 納管為 v1、v2 工作，重跑全部略過。（`test_adopt_outputs_includes_regenerated_versions`）
- [x] **場景 17d**：6 份備份 `keep=5` 預覽 1 份、不移動；套用後移到 `deleted/backups/`，`keep=0` 回 422；MCP `confirm=False` 不移動。（`test_backups_list_and_prune_move_to_deleted`）

## 6. 未決問題

- 無。

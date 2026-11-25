# SPEC-024：只記錄的課程連結既有 Gemini Notebook，以便產生新產出（心理學研究法）

- **狀態**：Draft（使用者 2026-11-25 決定先暫停：耗額度與 token）<!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-25
- **相關任務 / ADR**：TASK-041（決策 D4）／SPEC-014（record-only 課程）／SPEC-015（從既有檔案建立產出紀錄）／SPEC-021（學習網頁）／ISSUE-068

## 1. 目標

`115-1_CP30210` 心理學研究法是「只記錄」（record-only）課程：48 筆產出是從既有檔案登錄的（SPEC-015），本機沒有 `notebook_id`，所以不能產生學習網頁等新產出。遠端已有筆記本「[115-1] 心理學研究法***」（`04568153…`，151 個 Studio 項目），6 個章節 PDF 都已上傳過。

使用者要這門課也能產生新產出（例如學習網頁），但**不重複上傳、不重新產生已有的 48 份產出**。成功的樣子：課程連到既有筆記本、各講有正確的 `source_id`，只排入使用者勾選的新產出類型。

## 2. 使用情境

使用者在網頁課程「進階工具 → 連結既有 Gemini Notebook…」選遠端筆記本 → 預覽「講次 ↔ 遠端來源」對照表 → 確認 → 再到「變更產出模式…」只勾學習網頁 → 繼續課程。

## 3. 需求

- **必須 (Must)**：
  1. **預覽（唯讀、預設）**：列出遠端筆記本的來源（`list_sources`），依檔名（去副檔名、大小寫與空白正規化）對到本機各講的 PDF；輸出對照表：`matched`／`missing_remote`（本機有、遠端沒有）／`extra_remote`（遠端有、本機沒有）。
  2. **套用（需確認）**：寫入課程 `notebook_id` 與各講 `source_id`、`upload_status=uploaded`；**不上傳、不產生、不排入工作**。先備份資料庫（重用 `update.sh` 的備份片段）。
  3. 課程維持暫停；套用後提示使用者用「變更產出模式…」只勾選要新增的類型。改產出模式時，若課程是剛連結的 record-only 課程，預設不勾任何類型，避免 `set_course_profile` 依預設清單排入全部產出。
  4. 已有的 48 筆 `done` 產出紀錄不變；之後的「同步 Studio」（`sync_course_remote_artifacts`）可對應到遠端既有項目，不建立重複工作。
  5. 三入口：HTTP `POST /api/courses/{code}/link-notebook`（`dry_run` 預設 true）、MCP `link_course_notebook(course_code, notebook_id, dry_run=True, confirm=False)`、網頁對話框（遠端筆記本用下拉選單選，不手打 ID）。
  6. 只能連結到使用者自己帳號裡的筆記本；`notebook_id` 已存在的課程拒絕（409），要先解除連結。
- **可選 (Nice to have)**：對照不完整時，允許使用者在預覽表上手動選對應的遠端來源（下拉選單）。
- **不做 (Out of scope)**：自動上傳 `missing_remote` 的檔案（使用者另外決定）；刪除遠端 `extra_remote` 來源。

## 4. 介面 / API

`POST /api/courses/115-1_CP30210/link-notebook` `{"notebook_id": "04568153…", "dry_run": true}` →

```json
{"course_code": "115-1_CP30210", "notebook_id": "04568153…", "dry_run": true,
 "matched": [{"lecture_no": 1, "file": "Ch01-….pdf", "source_id": "…"}],
 "missing_remote": [], "extra_remote": [{"title": "…", "source_id": "…"}]}
```

錯誤：404 課程或筆記本不存在；409 課程已有 `notebook_id`；422 課程不是 record-only 也沒有講次。

## 5. 驗收標準

- [ ] Given 遠端 6 個來源與本機 6 講同名，When dry-run，Then `matched` 6 筆、資料庫不變。
- [ ] Given 檔名只差大小寫或空白，Then 仍對得上。
- [ ] Given 確認套用，Then 課程 `notebook_id` 與 6 講 `source_id` 寫入、佇列 0 筆新工作、48 筆產出不變、已建立備份。
- [ ] Given 課程已有 `notebook_id`，Then 回 409。
- [ ] Given MCP `confirm=False` 且 `dry_run=False`，Then 不寫入，只回說明。
- [ ] 實機（耗額度，使用者同意後）：只勾學習網頁並繼續 → 只排入 6 件學習網頁工作，沒有重新上傳。

## 6. 未決問題

- 使用者何時要開始（目前暫停）。
- 遠端 151 個 Studio 項目中，有些可能是本機沒有登錄的舊產出；是否要用 SPEC-015 一併登錄，另外決定。

# SPEC-029：網頁伺服器內建監看、講義遺失／更新提醒、文獻自動加入、macOS 通知

- **狀態**：Implemented（使用者 2026-11-26「照建議做」）<!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-26
- **相關任務 / ADR**：SPEC-014（watch）、SPEC-017（完成通知）、SPEC-020（課本偵測）、SPEC-027／028（新課程資料夾、補齊 01–05）、SPEC-012（文獻）

## 1. 目標

2026-11-26 盤點發現：`watch` 只有手動在終端機執行時才運作，使用者平常只開網頁，所以「新講義自動排程」等功能實際上都沒在跑。使用者同意先做五項不耗 Gemini 額度的自動化：

1. 網頁伺服器開著就一起監看（不用另外開 `watch`）。
2. 講次的 PDF 被刪除或改名時提醒。
3. 講次的 PDF 內容被更新（同檔名、內容不同）時提醒。
4. 文獻 PDF 放進 `scratch/literature/` 或課程的 `Literature_Review/` 就自動加入文獻清單。
5. 偵測到新課程資料夾、整本課本、講義遺失／更新時發 macOS 通知。

## 2. 使用情境

- 使用者只開「學習工作室」App：把老師新講義拖進 `02 Handouts/` → 自動登錄並排程（與 `watch` 相同）；跳出通知。
- 使用者在 Finder 誤刪或改名某講 PDF → 1 分鐘內跳出通知「講義遺失」，「批次排程」頁出現提示卡列出哪一講。
- 老師更新第 3 講講義、使用者覆蓋同名檔 → 通知「講義已更新」，提示卡說明筆記本裡還是舊版，由使用者決定是否重新上傳／重新產生。
- 把下載的論文放進 `scratch/literature/` → 1 分鐘內出現在文獻清單（不會自動查詢或下載）。

## 3. 需求

- **必須 (Must)**：
  1. **網頁內建監看**：設定 `WATCH_IN_WEB`（`.env`，預設 `true`；`AppConfig` 預設關，測試不啟動）。開啟時網頁伺服器啟動 `CourseWatcher`，行為與 `watch` 指令完全相同（SPEC-027 的講義／章節／整本課本規則、ISSUE-073 防護、整併暫停時不處理），關閉時停止。`watch` 指令保留。
  2. **講次檔案檢查**：對已登錄、未封存課程的每個講次，檢查 `study_dir/relative_path`：不存在 → `missing`；存在但 SHA-256 與資料庫不同 → `changed`。以檔案大小與修改時間快取雜湊，未變更的檔案不重算。只讀，不改資料庫、不上傳。
  3. **提示卡與三入口**：HTTP `GET /api/study/lecture-file-issues`、MCP `list_lecture_file_issues`（唯讀）、「批次排程」頁提示卡（遺失：「講義遺失：第 N 講 檔名」；更新：「講義已更新，筆記本裡還是舊版」）；可「知道了」略過（更新的略過以新雜湊為鍵，再次更新會再出現）。
  4. **文獻自動加入**：背景每 60 秒呼叫既有的 `sync_untracked_pdfs()`（只登錄，不查詢、不下載、不呼叫 Gemini）。
  5. **通知**：背景每 60 秒整理一次「新課程資料夾」「待切割的整本課本」「講義遺失／更新」；**第一次出現**的項目各發一則 macOS 通知（同一項目不重複；已通知清單存 `DATA_DIR/state/notified.json`，重啟不重發）。沿用 `NOTIFY_ON_COMPLETE` 開關（關閉時不發）。
  6. 第 4、5 與 SPEC-028 的補齊 01–05 共用同一個 60 秒背景執行緒；任何一步失敗只記 log，不影響其他步驟與下一輪。
- **不做 (Out of scope)**：自動切割、自動產生、自動排入 Gemini 筆記、自動重新上傳更新的講義、自動查詢文獻 DOI。

## 4. 介面 / API

```json
{"issues": [
  {"course_code": "115-1_CP31000", "course_name": "生涯諮商與實務", "lecture_no": 3, "filename": "Ch03-x.pdf",
   "relative_path": "01 Materials/Book/Ch03-x.pdf", "issue": "missing", "sha256": ""}
]}
```

## 5. 驗收標準

- [x] Given `WATCH_IN_WEB=true`，When 網頁伺服器啟動後在已登錄講義課程的 `02 Handouts/` 放入 PDF，Then 新講次登錄並排程；`WATCH_IN_WEB=false` 時不啟動監看。
- [x] Given 某講 PDF 被刪除，Then 檢查結果有該講 `missing`；改回原檔後消失。
- [x] Given 某講 PDF 內容被替換，Then 結果為 `changed` 並附新雜湊；未變更的檔案第二次檢查不重算雜湊。
- [x] Given 已封存課程的 PDF 遺失，Then 不列入。
- [x] Given `scratch/literature/new.pdf`，When 背景執行一輪，Then 文獻清單多一筆；不呼叫網路。
- [x] Given 新課程資料夾、整本課本、講義遺失各一，When 背景執行兩輪，Then 各只通知一次；重新建立服務（模擬重啟）後也不再通知；`NOTIFY_ON_COMPLETE` 關閉時不通知。
- [x] 背景一輪中某一步拋錯，Then 其他步驟仍執行。
- [x] HTTP、MCP、網頁提示卡三入口都有。

實作紀錄（2026-11-26）：`services/lecture_files.py`、`services/study_alerts.py`、`entrypoints/folder_sync.py`（`build_pass`）、`entrypoints/web_watch.py`（`start_web_watcher`、`start_background`）、`entrypoints/mcp_study_alerts.py`、`config.study_alerts_path`、`WATCH_IN_WEB`；`tests/test_background_alerts.py`（11 項）。測試時發現 macOS 可能在監看啟動後補送「啟動前剛建立的檔案」的 created 事件：處理方式與新檔相同（重新掃描、已存在的工作不重複排入），無害；測試改為等第 3 講本身出現。

## 6. 未決問題

- 無。

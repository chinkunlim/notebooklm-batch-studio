# SPEC-027：偵測新課程資料夾、加入時補建 01–05、watch 跟著課本章節

- **狀態**：Implemented（使用者 2026-11-26「兩個功能都做」，並問 watch 為何只看 02）<!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-26
- **相關任務 / ADR**：SPEC-014（watch、學習資料庫）、SPEC-016（登錄舊課）、SPEC-018／020（課本切割與偵測）、SPEC-025 R4a（ISSUE-073）

## 1. 目標

2026-11-26 實測發現三個落差：

1. 在 `study/<學期>/` 直接新建或貼上課程資料夾，程式不會提示；只在「學習紀錄」列為「未登錄」，而那裡的「登錄」是給舊學期用的（只記錄＋封存）。
2. 用「加入課程」加入**已經在 `study/` 裡**的資料夾時，不會補建 `01 Materials`～`05 Assignments`（只有從 `study/` 外面複製進來時才會建）。`domain/study_hierarchy.ensure_course_study_tree` 寫好了但沒人呼叫。
3. `watch` 只看 `02 Handouts`。這是 SPEC-018 之前的設計；現在兩門課都以 `01 Materials/<課本>/` 的章節為講次，`watch` 沒跟上。

成功的樣子：貼上新課程資料夾後，「批次排程」頁出現提示卡，一鍵打開加入課程精靈（已選好資料夾）；加入後五個分類資料夾都在；`watch` 會把新放進課本章節資料夾的章節加入講次，看到整本課本時提示去切割。

## 2. 使用情境

- 新學期開始，使用者在 Finder 建立 `study/115-2/CP__40000-新課/`，放入 PDF → 打開網頁「批次排程」→ 看到「偵測到新課程資料夾：CP__40000-新課」→ 按「加入課程…」→ 精靈已選好資料夾 → 照常選內容、設定、確認。
- 使用者用 `watch` 背景監看，把老師另外給的第 18 章 PDF 放進 `01 Materials/<課本>/` → 自動成為新講次（不自動排程）。

## 3. 需求

- **必須 (Must)**：
  1. **新課程資料夾偵測**：服務列出 `study/<學期>/` 裡符合課程資料夾格式、尚未登錄的資料夾，只列**目前學期以後**的（學期 ≥ 進行中〔未封存〕課程的最新學期；沒有進行中課程時，用 `study/` 裡最新的學期），避免把舊學期未登錄資料夾都列出來（舊學期仍用「學習紀錄」登錄）。回傳 `{term, folder, path, code, name, lecture_count}`。
  2. 三入口：HTTP `GET /api/study/new-course-folders`、MCP `list_new_course_folders`（唯讀）、網頁「批次排程」頁上方卡片（與「偵測到課本」同一區，每 60 秒更新），卡片按鈕「加入課程…」打開精靈並預選該資料夾；「略過」記住不再顯示（同課本卡片做法）。**只提示，不自動登錄、不自動排程。**
  3. **補建 01–05**：加入課程時，若資料夾已在 `study/<學期>/<資料夾>/`，補建缺少的分類資料夾（`StudyLayout.ensure_tree`；已有別名資料夾不重複建立）。不搬動、不改名任何既有檔案；放在資料夾最上層的 PDF 照樣當講次。預覽（dry-run）不建立任何資料夾。
  4. **watch 跟著講次來源**：
     - `02 Handouts` 新 PDF：維持現行（登錄並排程；課本課程略過，ISSUE-073）。
     - `01 Materials/<課本>/` 章節資料夾（有 `.textbook.json`）新 PDF：重新掃描講次（保留已上傳來源）並存檔，**不自動排程**；終端機顯示「已加入講次，到網頁按『開始生成』」。理由：網頁切割整本課本時也會寫入章節檔，若自動排程，一次切 17 章會排入約 170 件工作，違反使用者「切割不自動產生」的決定（SPEC-020）。
     - `01 Materials/` 最上層新 PDF（整本課本）：只在終端機提示「偵測到課本，請到網頁『批次排程』預覽並切割」，不自動切割。
     - `01 Materials` 其他子資料夾（文獻、參考資料）與 `03`～`05`：不處理。
- **不做 (Out of scope)**：自動登錄新課程、自動切割課本、watch 自動排程章節；網頁上建立「空白課程」。

## 4. 介面 / API

`GET /api/study/new-course-folders` →

```json
{"folders": [{"term": "115-2", "folder": "CP__40000-新課", "path": "/…/study/115-2/CP__40000-新課", "code": "115-2_CP40000", "name": "新課", "lecture_count": 1}]}
```

## 5. 驗收標準

- [x] Given 進行中課程在 115-1，`study/` 有未登錄的 `115-2/CP__40000-新課` 與 `114-2/CP__20000-舊課`，When 查詢新課程資料夾，Then 只回 115-2 那一筆。
- [x] Given 該資料夾登錄後，Then 不再出現在清單。
- [x] Given 沒有進行中課程，Then 用 `study/` 最新學期判斷。
- [x] Given `study/115-2/CP__40000-新課/` 只有最上層 PDF，When 加入課程，Then 五個分類資料夾都建立、PDF 仍在原位且是講次；When 只預覽，Then 不建立資料夾。
- [x] Given 課本課程，When watch 偵測到 `01 Materials/<課本>/Ch18-x.pdf`，Then 講次多一講、既有來源保留、佇列沒有新工作。
- [x] Given watch 偵測到 `01 Materials/整本.pdf`，Then 只提示、講次與佇列不變。
- [x] Given watch 偵測到 `01 Materials/Literature_Review/x.pdf`，Then 不處理。
- [x] HTTP、MCP、網頁卡片三入口都有；卡片按鈕會預選資料夾打開精靈。

實作紀錄（2026-11-26）：`services/new_course_folders.py`、`services/watcher.watch_kind`、`course_placement._ensure_course_tree`、`cli._add_chapter_lectures`；`tests/test_new_course_folders.py`（10 項）。隔離環境實測：卡片只列 115-2 的新資料夾 → 按「加入課程…」精靈已預選資料夾並帶入學期／課號／課名 → 加入後補建 01–05、PDF 留在原位、卡片消失；watch：新章節成為第 19 講且工作數不變、整本課本只提示、文獻資料夾不處理。

## 6. 未決問題

- 無。

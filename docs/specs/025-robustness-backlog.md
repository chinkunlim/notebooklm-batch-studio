# SPEC-025：穩定性待辦（筆記排程跨程序寫入、講次混用講義與課本、多本課本、notebooklm-py 升級把關）

- **狀態**：Draft <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-25
- **相關任務 / ADR**：SPEC-013、SPEC-018、SPEC-020、SPEC-021／ISSUE-070、ISSUE-071、ISSUE-072

## 1. 目標

把 2026-11-25 盤點出的已知限制寫成可驗收的需求。目前沒有一項擋住使用者的日常使用，依優先順序列出，各自可獨立實作。

| # | 限制 | 目前影響 | 優先 |
|---|---|---|---|
| R1 | 筆記排程跨程序同時寫入 | 實測比預期嚴重：兩程式各寫 60 筆只剩 61／120，另有 24 次寫入失敗 | ✅ 已完成（ISSUE-075） |
| R2 | notebooklm-py 內部 API | 升級套件時學習網頁可能壞掉 | ✅ 已完成（版本鎖定＋升級清單） |
| R3 | 同一門課有兩本課本資料夾 | 切割時用「PDF 同名資料夾」判斷，可能放錯資料夾 | 低 |
| R4 | 講次同時用老師講義與課本章節（「both」） | 用課本章節當講次的課，只要 `02 Handouts` 放進一份 PDF，掃描就整個改用講義當講次（`course_parser.py:124-126`），課本章節不再是候選；既有講次會怎樣尚未驗證 | R4a 已完成（ISSUE-073）；完整「both」有需要時再做 |

## 2. 使用情境

- R1：使用者在網頁按「排入筆記生成」，同時 Claude Code 透過 MCP 也排入另一門課。
- R2：使用者或 Agent 執行 `uv lock --upgrade-package notebooklm-py`。
- R3：一門課 `01 Materials/` 有兩本課本（主教材＋參考書），使用者放入第二本的整本 PDF。
- R4：老師開始提供每週講義（`02 Handouts`），同時課本章節也要當講次。

## 3. 需求

- **必須 (Must)**：
  - **R1 跨程序檔案鎖（已完成，ISSUE-075；鎖用標準函式庫 `fcntl` 直接放在 `NoteScheduler`，與 `course_rename_files` 相同做法，不需要 adapter 注入）**：`services/notes/note_scheduler.py` 的 `_update` 與 `status` 目前只用 `threading.Lock`（同一程序內有效）；網頁伺服器與 MCP 伺服器是不同程序，各自讀、改、寫 `DATA_DIR/state/note_schedule.json`，後寫的會蓋掉先寫的。改為在 `threading.Lock` 之外再加檔案鎖（`fcntl.flock` 鎖 `note_schedule.json.lock`，逾時 10 秒拋錯並記 log）；鎖的實作放 adapters 或 config 允許的工具層，由 entrypoints 注入，維持單向分層。
  - **R4a 講次來源切換防護（已完成，ISSUE-073）**：重現結果：章節講次被整批換成講義，並排入 10 件產出工作。`course_parser` 目前在 `02 Handouts` 有任何 PDF 時只用講義、否則才用課本章節。先寫測試重現「課本章節課程放入一份講義後重新掃描」的結果（講次是否被標為遺失、編號是否改變、是否排入新工作）。在完整「both」實作前，改為：課程已有來自課本章節的講次時，`02 Handouts` 新出現的 PDF 不改變講次來源，只記 log 並在網頁課程卡片提示「偵測到講義，但本課以課本章節為講次」；`watch` 對這種課程的 `02 Handouts` 事件也不排程。
  - **R2 升級把關（已完成：`pyproject.toml` 改為 `==0.8.6`、PROJECT_RULES「升級 notebooklm-py」清單、`tests/test_notebooklm_py_pin.py`）**：學習網頁用到的 notebooklm-py 內部介面（`client.artifacts._list_raw` 的列格式：類型代碼 10、`row[24]` 檔名與網址；`chat.ask` 觸發網頁生成；`artifacts.rename`；`_reject_html_download` 的行為）集中在一個 adapter，並以 fixture 測試（`tests/test_learning_site.py`、`tests/fixtures/notebooklm/site_row.json`）。在 `docs/standards/PROJECT_RULES.md` 加一條：升級 notebooklm-py 前後都要跑 `uv run python -m pytest tests/test_learning_site.py`，並用真實帳號列一次 Studio（唯讀）比對列格式；`uv.lock` 維持鎖定版本 0.8.6。
- **可選 (Nice to have)**：
  - **R3 多本課本**：`textbook_split._chapter_folder` 遇到兩個以上帶 `.textbook.json` 的資料夾時，不再預設用 PDF 同名資料夾，而是在預覽回應加 `folder_choices`，網頁「預覽並切割」對話框用下拉選單讓使用者選輸出資料夾（預設選章節檔名最相符的一個）。
  - **R4 講次來源「both」**：課程設定 `lecture_source = handouts | textbook | both`；`both` 時講次編號依「課本章節在前、講義依檔名排序在後」或使用者指定的順序；需要另寫 ADR（講次編號一旦產生就不能改，否則產出對不上）。
- **不做 (Out of scope)**：改用資料庫保存筆記排程（JSON 檔＋鎖已足夠）。

## 4. 介面 / API

- R1：無對外介面變更；鎖逾時時 HTTP 回 503「筆記排程忙碌中，請稍後再試」，MCP 回同樣訊息。
- R3：`POST /api/courses/{code}/textbooks/split`（dry-run）回應新增 `folder_choices: [{"path": "01 Materials/<書名>", "chapters": N}]`，確認時帶 `target_folder`（由下拉選單選）。
- R4：`set_course_options` 新增 `lecture_source`；預設 `textbook`（`02 Handouts` 空時）或 `handouts`，與現行行為相同。

## 5. 驗收標準

- [x] R1：Given 兩個程序各自建立 `NoteScheduler` 指向同一檔案，When 兩邊同時 `enqueue_course` 各 60 次（multiprocessing 測試），Then 檔案最後有 120 筆、JSON 有效。
- [x] R1：Given 鎖被另一程序持有超過逾時，Then 拋出可辨識的錯誤，HTTP 回 503。
- [x] R2：PROJECT_RULES 已加升級步驟；`tests/test_learning_site.py` 覆蓋列格式、改名、HTML 下載三處。
- [ ] R3（若做）：Given 兩個課本資料夾，When dry-run 切割，Then 回 `folder_choices` 兩筆，未指定 `target_folder` 時不寫入。
- [x] R4a（2026-11-25，`tests/test_lecture_source_guard.py`，ISSUE-073）：Given 課程有 3 個課本章節講次，When `02 Handouts` 放入 1 份 PDF 並重新掃描，Then 講次仍是那 3 個、編號不變、佇列沒有新工作，並出現提示。
- [ ] R4（若做）：Given `both`，Then 既有講次編號不變，新講次接在最後。

## 6. 未決問題

- R4 的講次排序規則要等真的有課程同時有講義與課本時，再和使用者確認。

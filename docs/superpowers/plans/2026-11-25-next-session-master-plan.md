# 下一個對話的總實作計畫（2026-11-25 交接）

> **For agentic workers:** 開工先讀本檔，再依「0. 開工步驟」做。各工作項目的細部步驟在各自的計畫檔；本檔是總表、決策點與注意事項。
> 需要實作的項目一律 SDD → BDD → TDD（核心規則 16），每項完成就 `agentctl commit`，**未經使用者明確同意不 push**。

**本對話完成的內容（已 commit）**：SPEC-016 學習資料夾網頁管理、SPEC-017（筆記檔案、完成通知、多版本納管、備份整理）、SPEC-018 課本切割與講次來源（兩門課章節已搬到 `01 Materials/<課本>/`）、SPEC-019 網頁缺口（產出模式、繼續生成、保留天數）、網頁路徑一律用選的、SPEC-020（課本偵測卡片、Gemini 筆記背景排程、額度到點續跑）、範本同步、一鍵安裝／更新腳本、ISSUE-069 修正、學習網頁提示詞與 SPEC-021／TASK-040 計畫。

---

## 0. 開工步驟

1. `python3 scripts/agentctl.py status`（看到 TASK-036、TASK-040）。
2. 讀 `docs/standards/PROJECT_RULES.md`、本檔、`docs/superpowers/plans/2026-11-25-learning-site-artifacts.md`、`docs/specs/021-learning-site-artifacts.md`。
3. 確認 `git log origin/main..HEAD`：交接時有 5 筆未推送（見 §1），**先問使用者要不要推**。
4. 跑基準：`uv run python -m unittest discover -s tests`（交接時 540 項 OK）與 `python3 scripts/agentctl.py check`（exit 0、0 警告）。
5. 網頁伺服器：交接時由上一個對話的瀏覽器面板啟動，對話結束後可能已停。用 `.claude/launch.json` 的 `web` 設定或使用者平常的方式啟動（`127.0.0.1:8768`）。
6. 第 2 節的決策點，需要時用一個問題問使用者，不要自行決定。

## 1. 交接時的狀態快照

- **Git**：`main`，未推送 5 筆：`5c6ac66`（SPEC-020）、`2f23fe8`、`7e7aa65`、`dae1dcd`（學習網頁提示詞）、`08265f1`（SPEC-021 與計畫）。工作區乾淨。
- **測試**：540 項 OK；`agentctl check` exit 0；`agentctl scan` 100/100。
- **Python**：`python3` 指令已指向 uv 的 3.11.17（`~/.local/bin/python3`）；專案 `.venv` 為 3.11.17。
- **真實資料（`projects-data/notebooklm-batch-studio`）**：
  - 3 門課：`115-1_CP31000` 生涯諮商與實務（full、筆記本 `28b9a258-7d77-40f6-8395-d9fbc2e253c0`、94 筆 done、10 講）、`115-1_CP30210` 心理學研究法（record-only、**沒有連結筆記本**、48 筆 adopted、6 講）、`115-1_GC68210` 和 AI 一起寫程式（record-only、0 講）。
  - 兩門課的章節 PDF 已搬到 `01 Materials/Career Counseling - Holism, Diversity, and Strengths/`（10 個）與 `01 Materials/Research Methods, Design, and Analysis 13th ed/`（6 個），各有 `.textbook.json`；`02 Handouts` 沒有 PDF，講次來自課本章節，編號與來源不變。
  - `backups/` 有 7 份資料庫備份（最新 `db-20261125-132103`）。
  - Gemini 網頁版已登入（55 cookies）；筆記排程是空的。
- **Gemini Notebook 實測留下的東西**：生涯諮商筆記本的 Studio 多了一份網頁「生涯諮商：生命生涯發展觀點 互動學習網頁」（id `c493b986-244e-4769-9612-87bcbc2d0ac1`）；下載的 HTML 只在上一個對話的暫存資料夾（可能已被清掉，需要時從 Studio 重抓）。
- **本機設定**：`.claude/launch.json`（不進 git）多了 `demo`（8771，示範頁）與 `site-test`（8772，指向上一個對話的暫存資料夾，已失效，可刪）。
- **舊的 MCP 程序**：上一個對話與 11/24 對話的 MCP 伺服器是舊程式；新對話會自動載入新程式。

## 2. 待使用者決定（一次問一個）

| # | 決策 | 選項 | 建議 |
|---|---|---|---|
| D1 | 推送 5 筆未推送 commit | 推上去／先不要 | 開工時先問；收工時 `agentctl closeout` 也會推 |
| D2 | TASK-040 執行方式 | Native（同一對話依序做）／Subagent-driven | Native：6 項任務彼此依賴介面，且實測細節已在計畫中 |
| D3 | 「Playwright 常被擋」是哪一個 | Gemini Notebook 登入（`login --browser`）／文獻圖書館瀏覽器／其他 | 先問清楚再決定 W3 範圍 |
| D4 | 心理學研究法要不要產生學習網頁等新產出 | 連結既有筆記本「[115-1] 心理學研究法***」（`04568153…`）並改成可產生的模式／維持只記錄 | 若要學習網頁就連結；改模式前先暫停課程，避免一次排入大量工作 |
| D5 | 是否停用舊版 `migrate-study-layout` | 停用（移除 MCP 工具、HTTP 回 410）／保留 | 建議停用（ISSUE-069 已修，但工具已無用途） |
| D6 | 補齊整本課本 | 使用者把整本 PDF 放進 `01 Materials/`（literature-parser 的 `input/processed/processed-books/` 有兩本） | 使用者自己複製；放好後網頁會出現課本偵測卡片 |

## 3. 工作項目

### W1：學習網頁產出（TASK-040，SPEC-021）— 主要工作

> **2026-11-25 第二個對話進度**：Task 1–5 已完成並 commit（`6b54d01`、`efc5341`、`0fbfc10`、`8bef9c0`、`44348b0`），Task 6 文件已更新；剩 Task 6 Step 2 真實資料驗收（耗額度，待使用者同意）。
> **Task 6 Step 2（A 版）已通過**：2026-11-25 生涯諮商第 1 講真實產生並下載（約 16 分鐘，job `ecc8815d`）。驗收時發現兩件事：①「重新生成」與 Ollama 精修會把通用提示詞塞進網頁工作，已修（`1d85b27`）；②課程若是暫停狀態，佇列不會領取工作（設計如此），驗收時暫時啟動課程、領取後立刻恢復暫停。剩 B 版（整本書）真實驗收。
> 與原計畫不同處：Task 5 改用 CSP `sandbox`＋儲存轉接器（使用者定案，ADR-016），因為原做法可經 `window.open` 取得同源頁面而呼叫 API。

- **計畫**：`docs/superpowers/plans/2026-11-25-learning-site-artifacts.md`（6 個任務，全部 TDD；Global Constraints、Review Focus 都寫在裡面）。
- **依 D2 選擇的方式執行**。
- 已驗證的關鍵事實（不要再重新摸索）：
  - `chat.ask(notebook_id, prompt, source_ids=[…])` 送出 `make me a site` 開頭的提示詞會觸發網頁生成；39 秒回覆「已送出生成請求」。
  - Studio 原始資料：類型代碼 `10`、狀態 `2`→`3`（約 11 分鐘）、`row[24] = [檔名.html, "text/html", 檢視網址, 下載網址, …]`、`row[15]` 建立時間；`client.artifacts._list_raw(notebook_id)` 取得原始列。
  - notebooklm-py 的下載器會拒絕 HTML（`_reject_html_download`），要用 storage_state 的 Google cookie 自行下載，只允許 `*.google.com`／`*.googleusercontent.com`。
  - fixture：`tests/fixtures/notebooklm/site_row.json`（網址已去識別化）。
  - 提示詞：`assets/prompts/notebook_site/learning_site.md`（A 每講、B 整本書；第一行 `make me a site` 必須保留）。
- **Task 6 Step 2 真實驗收會用 Gemini Notebook 額度，先問使用者。** 生涯諮商第 1 講已有一份測試網頁在 Studio，驗收時可直接讓佇列產生新的一份並比對。

### W2：心理學研究法連結筆記本（依 D4）

- 目標：讓 `115-1_CP30210` 可以產生學習網頁等新產出，又不重複上傳、不重新產生已有的 48 份產出。
- 步驟（先寫規格小節或併入 SPEC-021 附錄）：
  1. 確認遠端筆記本「[115-1] 心理學研究法***」（`04568153…`，151 個 Studio 項目）裡的來源與 6 個章節 PDF 是否一一對應（用 `list_sources` 比對檔名；唯讀）。
  2. 用既有入口設定 `notebook_id`、把各講 `source_id` 補上（需要新的小功能：依檔名比對補 `source_id`，dry-run 優先）；**不上傳**。
  3. 課程先暫停 → 改產出模式 → 只勾選要新增的產出（例如學習網頁）→ 確認排入的工作數 → 繼續。
- 風險：產出模式改成 full 會依預設清單排入所有產出（`set_course_profile` 會 enqueue）；務必先暫停並只選要的類型。

### W3：Playwright 被擋（依 D3）

- 現況：Gemini 網頁版已採「獨立啟動真 Chrome＋獨立資料夾＋CDP 連線」（`adapters/gemini/chrome_session.py`）；文獻瀏覽器是 Playwright `launch_persistent_context(channel="chrome")`（`adapters/literature/browser.py:154`），Gemini Notebook 登入走 notebooklm-py 的 `login`。
- 若被擋的是**文獻瀏覽器**：比照 Gemini，改用 `chrome_session.ensure_chrome` 啟動獨立資料夾（路徑由 config 提供，例如 `state/literature_chrome_profile`），再 `connect_over_cdp`；保留現有登入資料的遷移方式；ADR 記錄；測試用假的 CDP 端點。
- 若被擋的是 **Gemini Notebook 登入**：評估改為「真 Chrome 登入 → 匯出 storage_state 給 notebooklm-py」；先確認 notebooklm-py 是否支援讀取 Chrome profile 的 cookie。
- 一律不在程式中輸入或保存 Google 密碼（PROJECT_RULES §4）。

### W4：停用 `migrate-study-layout`（依 D5）

- HTTP `POST /api/courses/migrate-study-layout` 回 410 並說明改用 `consolidate`；MCP 工具 `migrate_study_layout` 移除或只回說明；保留服務程式碼供測試，或一併刪除並更新測試、README、SPEC-012 註記；寫 ADR。

### W5：我可以自己驗證的項目

- SPEC-020 課本偵測卡片的畫面：在暫存 `DATA_DIR` 放一本有書籤的 PDF，用 `web-verify`（8769）或測試伺服器看卡片與「預覽並切割」流程（不要動真實資料）。
- SPEC-020 Gemini 額度續跑：真實情況下次遇到上限時觀察筆記排程卡片的「預計 HH:MM 繼續」並確認到時間會接著跑。
- SPEC-017 完成通知：下次真的跑完一門課的產出時確認 macOS 通知。

### W6：使用者實機確認（TASK-036）

`.agents/tasks/TASK-036-checklist.md` 未完成：#1 心理學研究法交一次測驗、#2 真 iPhone 版面（模擬已通過）、#3 工作台 11 張工具卡、#4 Anki／XMind 匯入、#5 Obsidian 標籤、#6 提問抽屜、#7 Open WebUI、#9 watch 監看（注意：講次來源已改成課本章節，`02 Handouts` 空的）、#10 scratch 歸檔、#12／#13 真實產出（耗額度）、#14 網頁端對端、#15 八階段、#16 登錄舊學期課程、#19 切割整本課本、#20 完成通知、#21 修改課程名稱。

### W7：收尾與整理

- 刪除 `.claude/launch.json` 的 `site-test` 設定（指向已失效的暫存資料夾）。
- `backups/` 已 7 份，使用者同意後用「設計與自訂 → 資料庫備份 → 整理舊備份」（移到 `deleted/backups/`，不刪除）。
- 生涯諮商的空資料夾 `01 Material`、`02 Handout`：使用者自行決定是否刪除。
- 對話結束時依 `session-closeout` skill：先更新所有 md（ARCHITECTURE、README、SPECS、CHANGELOG、LATEST），再 `agentctl closeout`（會 commit 並推送；使用者說「收工」即視為同意推送）。

## 4. 注意事項（上一個對話踩過的坑）

- **檔案行數上限 500**：`services/orchestrator.py`（499）、`config/settings.py`（約 483）、`adapters/db/queue_repository.py`（492）、`domain/notebooklm_protocol.py`（494）、`services/learning_record.py`（489）、`studio-batch.js`（474）都接近上限，新功能放新檔案。
- **函式參數 ≤ 4（含 keyword-only）**：需要更多就用資料物件或建構後設定屬性（例：`WorkerPool.on_course_complete`）。
- **分層**：services 不能 import adapters；需要外部功能時由 entrypoints 注入（例：`course_complete_hook(cfg, send_notification)`）。
- **DATA_DIR 子路徑**只能在 `config/`（`config/data_paths.py` 的 mixin 放新路徑）。
- **check 誤報**：CSS 的 `#id` 選擇器被當成刪除註解；commit 後就消失。
- **ruff 也會格式化 Markdown 裡的 Python 程式碼區塊**：計畫或規格文件裡的 ```python 範例沒排好，`agentctl check` 會失敗（2026-11-25 學習網頁計畫就因此讓 check exit 1）。寫完文件先跑 `uv run ruff format <檔案>`。
- **網頁上路徑一律用選的**（`tests/test_path_pickers.py` 會擋手打路徑的欄位）。
- **按鈕路由測試**（`tests/test_button_routes.py`）不接受 `/api/...${變數}` 這種字串拼接，前端呼叫要寫完整路徑。
- **macOS `/var` 是 `/private/var` 的連結**：比較路徑前先 `resolve()`。
- **pypdf 7 改了 API**（`compress_identical_objects` 參數、`add_outline_item` 關鍵字參數）；專案目前鎖 6.21.1。
- **record-only 課程沒有 `notebook_id`**：任何要呼叫 Gemini Notebook 的功能都要先檢查（ISSUE-068）。
- **真實資料**：改資料庫或搬檔前一律先備份（`update.sh` 的備份片段可重用）、先 dry-run、再取得使用者同意。

## 5. 補充：仔細檢查後補上的遺漏項目

- **待補紀錄（核心規則 4）— 2026-11-25 第二個對話已完成**：
  - [x] [ISSUE-070](../../known-issues/070-notebooklm-py-rejects-html-download.md)：notebooklm-py 的 `_reject_html_download` 把 HTML 產出誤判為登入頁（已規避，對應 SPEC-021 Task 3；實作時加 `Refs: ISSUE-070` 並補 KNOWN_ISSUES 總表的測試欄）。
  - [x] `docs/TEMPLATE_FEEDBACK.md`：code-review-guard 把 CSS `#id`、Markdown `#` 標題當成「刪除註解」誤報。
- **第二次盤點補上的小項目（2026-11-25）**：
  - Antigravity 的 MCP 伺服器也要重新載入才會用到新程式（之前只寫了 Claude Code 這邊）。
  - 未推送 commit 已增為 7 筆（另加 `f3366e1`、`8ef2eee`），D1 以 `git log origin/main..HEAD` 為準。
  - `DATA_DIR/output/` 實際只剩兩個 `.DS_Store`；`midterm-submission/`、`input/courses/` 已不存在，不用再處理。
- **TASK-036 清單第 1 節的整理工作**（不在表格裡，容易漏）：關閉舊對話（舊 MCP 程序）、用平常方式啟動伺服器、刪除空的 `DATA_DIR/output/`（0 個檔案、資料庫沒有指向它，使用者尚未決定）、整理 `backups/`。
- **尚未實測**：
  - 學習網頁提示詞 **B 版（整本書）** 只寫好、沒在真實 Gemini Notebook 跑過；W1 驗收時要各跑一次 A、B（耗額度，先問）。
  - `./scripts/install.sh` 全新安裝流程沒有從頭跑過（只驗證過 `update.sh`）；在暫存資料夾的乾淨 clone 測，**不要**讓它寫到真實 `.env`／`DATA_DIR`。
  - 課本偵測卡片、Gemini 額度到點續跑、完成通知（見 W5）。
- **已知限制（列入對應規格的未決問題）**：
  - 筆記排程的 `note_schedule.json` 只有程序內鎖；網頁伺服器與 MCP 程序同時寫入時可能遺失更新（機率低）。
  - SPEC-018：同一門課同時用講義與課本章節當講次（「both」）尚未支援。
  - SPEC-021 不做：同步使用者在 Gemini Notebook 網頁上手動做的網頁（`sync_service`）。
  - 依賴 notebooklm-py 私有 API `_list_raw` 與原始列位置 `row[24]`；升級套件前先跑 `tests/test_learning_site.py`。
  - 生涯諮商與實務 Ch01：現有檔案 20 頁、書籤偵測為 18 頁（p.23–40）；切割整本時會略過現有 Ch01，若要用書籤版需使用者決定。
  - `python3` 預設是用 `uv python install --default`（實驗性選項）設定的。
- **已更正的文件**：SPEC-015 §6 兩項已由 SPEC-017 完成；SPEC-018 真實資料驗收已勾選（2026-11-25 套用）。
- **收工流程尚未執行**：`.agents/conversations/` 的本次對話紀錄要由 `agentctl closeout` 產生（使用者說「收工」時執行，會推送）。

# notebooklm-batch-studio

**Gemini Notebook 學習工作室**（Gemini Notebook 即原本的 NotebookLM，2026-07-16 改名）是一套專為大學與進修課程設計的自動化講義複習套件生成系統。使用者只需將每門課的講義 PDF 放入對應的資料夾，程式便會自動建立 Google Gemini Notebook 筆記本、上傳 PDF、逐份單獨勾選來源並生成完整學習套裝（音訊摘要 Audio Overview、30 題階梯式測驗 Quiz、重點閃卡 Flashcards、心智圖 Mind Map、期末模擬考 Mock Exam），自動將產出更名、轉檔為 Markdown 與列印用 PDF 下載至本機，並提供本機 Web 儀表板與 MCP 伺服器供 AI 助手對話操作。

## 核心特色

- 📚 **資料夾批次映射**：一個資料夾 = 一門課 = 一本 Gemini Notebook 筆記本，自動剖析講義編號與主題名稱，支援本機資料夾挑選器。
- 🎯 **單一來源精準生成**：生成每講教材時只勾選該份 PDF，確保產出內容精確不互相污染。
- 📝 **30 題階梯式題庫**：自動整併基礎題、理解題與模擬考題，支援品質檢驗；題數不足時自動隔離至 `needs_review/`。
- 🎓 **學生研讀工作台 (Study Portal)**：線上互動測驗即時評分、個人錯題筆記本、3D 翻轉閃卡、分段音訊播放器與一鍵匯出 Anki 間隔重複牌組。
- 📄 **多格式轉檔輸出**：測驗轉為 Markdown 與列印用 PDF；閃卡輸出為 Markdown 與 Anki CSV；心智圖輸出為 Markdown 與 Mermaid；資訊圖表自動適配直式、A4 PDF、iPad Air 4 與 MacBook Pro 14 吋；報告輸出排版 HTML。
- 🔁 **版本化重新生成**：支援在不覆蓋既有產出的前提下生成新版本（v2、v3…），筆記本與檔名同步自動版號管理。
- 🔄 **斷點續傳與配額防護**：讀取 Gemini Notebook 即時額度表，支援 5 小時與每週額度窗預估，額度用盡自動進入安全等待並排程無縫續跑。
- 🧠 **學習心理學輔助**（SPEC-008）：內建離線 PDF.js 講義閱讀器並色彩對應核心重點、艾賓浩斯遺忘曲線記憶強度評估、連續天數熱圖、作答信心比對（sure-but-wrong 盲點警示）、跨講混合複習、蘇格拉底式引導家教與 25 分鐘番茄鐘。
- 📅 **學生研讀計畫**（SPEC-007）：動態規劃今日研讀「Today」清單、考前倒數天數、AI 詳解自動快取與間隔複習排程。
- ⚙️ **產出細部自訂**（SPEC-006）：支援個別產出覆寫題目數、難度、語言、圖表風格與投影片格式（PDF/PPTX），三層設定自動繼承。
- 🎨 **研讀工作室與外觀自訂**（SPEC-009，**規劃中、尚未實作**；原型在 `docs/design/`）：奢華黑膠擬態唱盤（非均向性光澤、機械唱臂落針動態、270° 環形進度弧線軌道）、9 大產出物全景平鋪九宮格矩陣（免分頁切換）、頂部第 4 主分頁自訂設計、全設備雙軌 RWD 根治與個人頭像自訂。
- 🌐 **三大操作入口**：完整 CLI 指令集、FastAPI 本機儀表板（`127.0.0.1:8768`），以及供 Claude Code、Antigravity、Open WebUI 呼叫的 MCP 伺服器集群與 OpenAPI 路由。

## 快速開始

### 1. 第一次在這台電腦使用

1. 取得程式（已在本機則略過）：

```bash
git clone <repo-url> && cd notebooklm-batch-studio
```

2. 檢查並修復環境（啟用 git hooks、建立 `.env`、建立 `DATA_DIR`、檢查 uv）：

```bash
python3 scripts/agentctl.py doctor --fix
```

3. 打開 `.env` 設定資料目錄與埠號（`.env` 不會進 git，資料全數存放於專案外的 `DATA_DIR`）：

```bash
# 預設位置例如：
DATA_DIR=/Users/username/Desktop/projects-data/notebooklm-batch-studio
HTTP_PORT=8768
```

4. 安裝依賴（uv sync 到專案內 `.venv/`）：

```bash
python3 scripts/agentctl.py setup --install
```

5. 登入 Gemini Notebook（會開啟瀏覽器，由你親自登入 Google 帳號一次；憑證保存於 `~/.config/notebooklm-batch-studio/`，權限 600）：

```bash
uv run notebooklm-batch-studio login --browser
```

之後可用下列指令確認憑證是否存在且有效（只檢查，不會開瀏覽器）：

```bash
uv run notebooklm-batch-studio login
```

---

## 日常操作指令 (CLI)

### 1. 批次處理課程講義

將包含 PDF 講義的資料夾加入排程並開始處理：

```bash
uv run notebooklm-batch-studio batch /path/to/BIO101 /path/to/CS101 --profile full
```

產出組合選項 (`--profile`)：
- `full`：完整學習包（Audio, Quiz × 3, Flashcards, Mind Map, 考前模擬考）
- `quiz-only`：僅生成各講 30 題測驗
- `exam-prep`：期末考衝刺包（各講模擬考題、整門課模擬考、全課程總心智圖）

加上 `--wait-quota`：額度用完時不結束，等額度重置後自動繼續，全部完成才結束。

### 2. 檢視進度與狀態

```bash
uv run notebooklm-batch-studio status
```

### 3. 斷點續傳 (Resume)

若因碰觸每日額度上限或中途暫停，重啟後執行續跑即可繼續未完成的工作：

```bash
uv run notebooklm-batch-studio resume
```

### 4. 目錄即時監看 (Watcher)

監聽 `DATA_DIR/input/courses/` 底下所有課程資料夾（不需要也不接受路徑參數），當有新講義 PDF 存入且寫入完成時自動加入處理：

```bash
uv run notebooklm-batch-studio watch
```

### 5. 啟動 Web 儀表板與 MCP 伺服器

**最簡單：雙擊開啟。** 第一次先建立 App，以後雙擊「Gemini Notebook 學習工作室」即可（可以拖到 Dock）：

```bash
zsh scripts/build_mac_app.sh
```

雙擊後：
- 伺服器沒開的話，會在背景自動啟動，log 寫到 `DATA_DIR/logs/launcher.log`。
- 用 Chrome 的 App 模式全螢幕開啟：沒有網址列、分頁、書籤，也就是「專注模式」。按 `⌃⌘F` 可以離開全螢幕。
- 沒有安裝 Chrome 時，改用預設瀏覽器開啟。側欄底部的「專注模式」也能切換全螢幕。

也可以手動啟動本機 FastAPI 服務（預設綁定 `http://127.0.0.1:8768`；埠號被佔用時會顯示是哪個程式在用。全機埠號總表見 `00 init_dev_env/PORTS.md`）：

```bash
uv run notebooklm-batch-studio web
```

- 網頁儀表板：瀏覽器開啟 `http://127.0.0.1:8768/`
- OpenAPI 規格與文件：`http://127.0.0.1:8768/docs`（可作為 Open WebUI 工具伺服器）
- MCP 端點：供 AI 代理人透過 MCP Client 連線協同

網頁服務啟動後會自動處理佇列（`.env` 的 `AUTO_START_QUEUE=true`）。額度用完的工作會顯示「⏸ 等待額度，預計 HH:MM 自動繼續」，網頁服務開著時間到就自己接著跑。

網頁有四個頁面（左側側欄），側欄底部是「使用方法」「專注模式」「設計與自訂」：
- **研讀總覽**：今天的學習循環（照研讀計畫）、章節路線、掌握程度、各講步驟、記憶強度與本週紀錄；「繼續研讀」回到上次停的地方。
- **研讀工作室**：選課程與講次（課程目錄），唱盤播放該講的語音摘要（黑膠、弦波、環形、聲譜四種視覺；播放中離開會縮到側欄成迷你播放器）。工作台把講義（PDF 與重點畫線）、影片摘要、報告、心智圖、資訊圖表、簡報、資料表、測驗、學習卡、AI 家教放在同一處；三種版面、四種排列、可調欄寬與收合。
- **弱點複習**：錯題集（詳解、問 Gemini Notebook 為什麼、匯出 Anki）與今日到期學習卡。
- **批次排程**：課程清單、課程設定（語言、考試日期、題數、各產出物的形式、補充指示）、產出內容、依講次分組的生成項目（Prompt、單項設定、下載、重新生成 v2/v3…）、進行中與額度；「加入課程」用點選資料夾的精靈。額度用完的工作會在額度重置後自動繼續。
- **設計與自訂**：配色（五組＋自訂）、日光 / 暗夜 / 自動、介面風格、研讀版面、產出物排列、播放器視覺、頭像、字型。

設定記在這台電腦（`DATA_DIR` 的 SQLite，`/api/preferences`，ADR-009）：換瀏覽器或清快取都還在，「全部恢復預設」一鍵還原。

字型與圖示都內建在 `static/vendor/`，離線也能顯示。「設計與自訂 → 字型」可以：
- 內文、標題各自選：內建 Noto Sans / Serif TC、Mac 的蘋方 / 宋體，或已下載的 Google Fonts。
- 輸入 Google Fonts 上的字型名稱（例如 `LXGW WenKai TC`）按「下載」，存到 `DATA_DIR/fonts/`，之後離線也能用（MCP：`install_google_font`）。

---

## 開發與測試

執行靜態架構審查（註解、分層、秘密檢查、目錄樹檢查）：

```bash
python3 scripts/agentctl.py check
```

執行完整單元與離線整合測試：

```bash
uv run python -m unittest discover -s tests -v
```

---

## 和 AI Agent 一起開發

本專案使用標準 Agent 開發工作流程。使用 Claude Code、Antigravity、Cursor 等工具時，直接以口語對話下達指令：

| 你說 | Agent 會做 |
|---|---|
| 「開工」「繼續上次的」 | 查看交接看板、上次下一步、待接手任務 (`agentctl status`) |
| 「新功能：…」 | 建立任務卡，遵循 TDD 撰寫測試與程式碼 |
| 「commit」 | 通過檢查後執行本機 commit（英文訊息，不自動推送） |
| 「去上課」「先暫停」 | 記下目前進度，儲存 WIP 狀態 |
| 「收工」 | 跑測試、生成逐字稿與摘要、更新交接看板、commit |
| 「推上去」 | 列出未推送 commits，等待使用者確認後推送 |
| 「出版本」「專案完成了」 | 執行完工驗收；`--tag` 時自動升版並建立本機 tag |

完整對照表請參閱 [`AGENTS.md`](AGENTS.md)。

---

## 文件索引 (Docs Map)

- [`AGENTS.md`](AGENTS.md) — Agent 團隊規則與標準作業流程
- [`.agents/handoff/LATEST.md`](.agents/handoff/LATEST.md) — 即時交接看板與歷史記錄
- [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) — 系統架構圖、五層依賴與核心流程
- [`docs/architecture/PROJECT_TREE.md`](docs/architecture/PROJECT_TREE.md) — 完整目錄樹與檔案標記
- [`docs/specs/SPECS.md`](docs/specs/SPECS.md) — 需求規格書總表（SPEC-001 ~ SPEC-008）
- [`docs/adr/DECISIONS.md`](docs/adr/DECISIONS.md) — 架構決策記錄庫（ADR-001 ~ ADR-006）
- [`docs/known-issues/KNOWN_ISSUES.md`](docs/known-issues/KNOWN_ISSUES.md) — 已知問題與踩坑排查庫（ISSUE-001 ~ ISSUE-024）
- [`docs/standards/PROJECT_RULES.md`](docs/standards/PROJECT_RULES.md) — 本專案特有規則（領域名詞、埠號 8768、安全禁忌）
- [`alembic/DB.md`](alembic/DB.md) — 資料庫模型遷移與 11 張實體資料表綱要指南 (SQLite / SQLAlchemy)

# notebooklm-batch-studio

**NotebookLM Batch Studio** 是一套專為大學與進修課程設計的自動化講義複習套件生成系統。使用者只需將每門課的講義 PDF 放入對應的資料夾，程式便會自動建立 Google NotebookLM 筆記本、上傳 PDF、逐份單獨勾選來源並生成完整學習套裝（音訊摘要 Audio Overview、30 題階梯式測驗 Quiz、重點閃卡 Flashcards、心智圖 Mind Map、期末模擬考 Mock Exam），自動將產出更名、轉檔為 Markdown 與列印用 PDF 下載至本機，並提供本機 Web 儀表板與 MCP 伺服器供 AI 助手對話操作。

## 核心特色

- 📚 **資料夾批次映射**：一個資料夾 = 一門課 = 一本 NotebookLM 筆記本，自動剖析講義編號與主題名稱。
- 🎯 **單一來源精準生成**：生成每講教材時只勾選該份 PDF，確保產出內容精確不互相污染。
- 📝 **30 題階梯式題庫**：自動整併基礎題、理解題與模擬考題，支援品質檢驗；題數不足時自動隔離至 `needs_review/`。
- 📄 **多格式轉檔輸出**：測驗轉為 Markdown 與排版精美的 PDF；閃卡輸出為 Markdown 與 Anki 匯入用格式；心智圖輸出為 Markdown 與 Mermaid 語法。
- 🔄 **斷點續傳與配額防護**：SQLite 工作佇列追蹤任務進度，遇每日配額上限或 Rate Limit 自動退避，隨時支援一鍵無縫續跑。
- 🌐 **三大操作入口**：完整 CLI 指令集、FastAPI 本機儀表板（`127.0.0.1:8768`），以及供 Claude Code、Antigravity、Open WebUI 呼叫的 MCP 伺服器與 OpenAPI 路由。

---

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

5. 登入 NotebookLM（會開啟瀏覽器，由你親自登入 Google 帳號一次；憑證保存於 `~/.config/notebooklm-batch-studio/`，權限 600）：

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

啟動本機 FastAPI 服務（預設綁定 `http://127.0.0.1:8768`）：

```bash
uv run notebooklm-batch-studio web
```

- 網頁儀表板：瀏覽器開啟 `http://127.0.0.1:8768/`
- OpenAPI 規格與文件：`http://127.0.0.1:8768/docs`（可作為 Open WebUI 工具伺服器）
- MCP 端點：供 AI 代理人透過 MCP Client 連線協同

網頁服務啟動後會自動處理佇列（`.env` 的 `AUTO_START_QUEUE=true`）。額度用完的工作會顯示「⏸ 等待額度，預計 HH:MM 自動繼續」，網頁服務開著時間到就自己接著跑。

課程詳細頁可以：
- 看狀態統計：完成、生成中、排隊中、等待額度、需審查、失敗各有幾項（每 15 秒自動更新）。
- 按「🔁 重新生成」：產生新版本（v2、v3…），舊版保留；NotebookLM 標題加「 (v2)」，本機檔名加「_v2」。
- 打開「⚙️ 產出設定」：資訊圖表方向 / 詳細程度 / 風格、語音形式與長度、投影片格式與下載格式（PDF / PPTX）、影片形式與風格、測驗與閃卡題量。資訊圖表預設直式，並另存 A4 PDF、iPad Air 4、MacBook Pro 14 吋三個版本。
- 頁首「📘 使用方法」：操作步驟、每一講的讀書順序、考前安排與額度說明（也可用 `GET /api/usage-guide` 或 MCP `get_usage_guide` 取得）。
- 報告除了簡報文件、讀書指南、部落格文章，還有「概念解說」（concept explanation），報告會另存排版好的 HTML 頁面。NotebookLM 新的「互動式」報告目前 notebooklm-py 還不支援，需在 NotebookLM 網頁手動產生。
- 頁首「🏷️ 命名規則」說明每種產出的意思、NotebookLM 標題與本機檔名，例如 quiz_1 是基礎（easy）、quiz_2 是理解（medium）、quiz_3 是模擬考（hard），各 30 題。

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
- [`docs/specs/SPECS.md`](docs/specs/SPECS.md) — 需求規格書總表（SPEC-001 ~ SPEC-004）
- [`docs/adr/DECISIONS.md`](docs/adr/DECISIONS.md) — 架構決策記錄庫（ADR-001 NotebookLM 存取機制）
- [`docs/known-issues/KNOWN_ISSUES.md`](docs/known-issues/KNOWN_ISSUES.md) — 已知問題與踩坑排查庫
- [`docs/standards/PROJECT_RULES.md`](docs/standards/PROJECT_RULES.md) — 本專案特有規則（領域名詞、埠號 8768、安全禁忌）
- [`alembic/DB.md`](alembic/DB.md) — 資料庫模型遷移指南 (SQLite / SQLAlchemy)

# 給專案模板的改進建議 (TEMPLATE_FEEDBACK)

> 使用者提出「以後每個專案都要這樣」的規則或習慣時，Agent 記在這裡（不直接改模板）。
> 使用者之後決定是否把它更新到專案模板（`01 project_template`），讓所有新專案都有。
>
> - 每條建議一列；**狀態**只用：`待決定`（新建議）、`已採用`（母版已更新）、`不採用`。
> - 使用者在母版執行 `python3 scripts/collect_feedback.py`，會一次列出所有專案中「待決定」的建議。

| 日期 | 建議 | 來源（對話 / 任務） | 狀態 |
|---|---|---|---|
| 2026-11-01 | setup_env.py 的 check_dependencies 應利用 IMPORT_HINTS 比對 PyPI 映射名稱（如 PIL -> Pillow），避免誤判未宣告第三方套件 | TASK-009 | 已採用（v3.6.0） |
| 2026-11-01 | 埠號改以 `00 init_dev_env/PORTS.md` 為全機唯一總表：`LOCAL_AI_ENVIRONMENT.md` 指向它；新專案從「下一個可用的埠號」取號並回填；伺服器啟動前檢查埠號，被占用時列出佔用的程式並停止（**補充：偵測 socket 與 Linux CI 測試端 socket 皆須啟用 `SO_REUSEADDR`，避免剛停服的 `TIME_WAIT` 造成誤判**） | 使用者：「port number 似乎會衝突，是不是要記錄在開發環境裡面」（`ISSUE-025`, `ISSUE-027` 補充） | 已採用（v3.6.0） |
| 2026-11-01 | 有網頁的專案都附一鍵開啟的 macOS App（雙擊後，服務沒開就在背景啟動，再用 Chrome `--app` 全螢幕開啟，沒有網址列） | 使用者：「有沒有可能可以直接點擊打開，方便使用者？」 | 待決定 |
| 2026-11-15 | 網頁開發流程固定順序：「設計風格與理念對齊 (`DESIGN.md`) → 實作功能（HTTP / MCP / Web UI 同步）→ 桌面 / 平板 / 手機三視口自適應檢查（不強制固定特定版型）→ 參考線與排版對齊 → 動畫/過渡一致性審查（同類功能必須一致、節奏溫潤不急促）→ `design_audit.py` + `agentctl check`」 | 網頁設計與功能反覆打磨經驗 | 待決定 |
| 2026-11-15 | 網頁介面內建「完整階層路徑參考線（Breadcrumb Layout Guides）」：點擊框線應複製含視口與父層的完整路徑（如 `[desktop 1440px] section#view-study > div#splitStage > div#panelReports > button (112x32)`），而非只有最內層 child 名稱，讓 Agent 一次精準定位 | 使用者：「目前參考線只有 child 名字，分析時還要花時間找」 | 待決定 |
| 2026-11-15 | 同類 UI 元件必須維持動畫、語彙與自動化互動習慣一致性：(1) 同一設計語彙（純文字膠囊、不混入 emoji）；(2) 所有同類元件（彈窗、抽屜、Popover、分頁切換）共用統一 CSS Motion Tokens（`--dur-hover` / `--dur-slide` / `--ease`）；(3) 跨專案通用的自動化互動習慣（如標準化的 Expand / Collapse 展開收合邏輯與浮動還原按鈕）應模組化複用 | 使用者：「動畫要統一、版位顧慮桌面/平板/手機，expand/collapse 等自動化習慣可複用」 | 已採用（v3.6.0，CSS Motion Tokens 已納入 `web_pack` 與 `taste_design.md`） |
| 2026-11-15 | 複雜版面支援「使用者直接拖動／拉動微調（Layout Tune Mode）」：依 桌面 / 平板 / 手機 視口各自記憶拖拉尺寸（自動吸附 8px 網格），並可一鍵複製微調規格（Copy Layout Diff）給 Agent，取代純靠文字反覆描述排版細節 | 使用者：「有些用文字描述，還不如使用者拖动、拉动等直接调整」 | 待決定 |
| 2026-11-15 | 跨裝置互動與觸控筆規範：所有功能必須同時支援桌面、平板與手機（`@media (pointer: coarse)` 放大觸控熱區 ≥ 36px、拖曳把手加 `touch-action: none`、無鍵盤裝置必備按鈕入口），且筆記/閱讀器須原生支援 iPad Apple Pencil（偵測 `pointerType === 'pen'` 自動落筆書寫／螢光筆、手指維持捲動與雙指縮放） | 使用者：「所有功能，都要支援平板和手机，ipad需支援apple pencil。」 | 待決定（`pointer: coarse` ≥ 44px 已納入 v3.6.0；Apple Pencil 待決定） |
| 2026-11-22 | `[P0][API/DB]` FastAPI + SQLAlchemy（`--with api --with db`）預設內建 `ContextVar` Request-Scoped DB Session 中介層（`DbSessionScopeMiddleware`，請求結束自動 `registry.remove()`），背景任務另用獨立 `session_scope` provider，根治執行緒池連線洩漏 | 專案架構提煉（`api.py`, `ISSUE-023`） | 已採用（v3.6.0） |
| 2026-11-22 | `[P0][API/安全]` 本機 Web 預設採用 `NoCacheStaticFiles`（送 `Cache-Control: no-cache` 避免瀏覽器／Safari 沿用舊靜態檔）、可配置白名單之 `HostValidationMiddleware`（兼顧本機安全與 Tailscale HTTPS 跨裝置存取），以及下載路由一律用 `Path.resolve()` + `is_relative_to(root)` 防路徑穿越 | 專案架構提煉（`api.py`, `http/artifacts.py`, `ISSUE-010`, `ISSUE-028`） | 已採用（v3.6.0） |
| 2026-11-22 | `[P0][測試]` `--with api` 預設內建「前端 API 路徑 vs OpenAPI 自動契約測試」（靜態掃描前端 `fetch('/api/...')` 比對 `app.openapi()['paths']`，0.1 秒離線攔截死按鈕）與「無瀏覽器 UI 結構不變量回歸測試」 | 專案架構提煉（`test_button_routes.py`, `test_dummy_user_simulation.py`, `ISSUE-024`, `TASK-019`） | 已採用（v3.6.0） |
| 2026-11-22 | `[P1][分層]` 在 `domain/` 以 `typing.Protocol` 定義所有 Repository 與外部客戶端介面，讓 `services` 100% 零引用 `adapters` 並通過嚴格 `mypy`；搭配單一 `DummyClient` + 記憶體 SQLite + 真實 FastAPI `TestClient` 執行零網路全流程端到端模擬測試 | 專案架構提煉（`domain/repositories.py`, `tests/dummy_client.py`, `TASK-017`） | 已採用（v3.6.0） |
| 2026-11-22 | `[P1][入口拆分]` 中大型專案的入口層採「平行領域拆分」：主檔 `api.py` / `mcp_server.py` 僅保留組裝根（Composition Root）與 `lifespan`，業務路由拆為 `entrypoints/http/<domain>.py`（`APIRouter`）並對應 `entrypoints/mcp_<domain>.py`（`register_<domain>_tools`），防止單檔膨脹觸發審查門檻 | 專案架構提煉（`entrypoints/http/`, `entrypoints/mcp_*.py`） | 已採用（v3.6.0 `fastapi_mcp.md`） |
| 2026-11-22 | `[P1][背景佇列/AI]` 背景任務框架規範：(1) 任務規劃（Planner）與執行池（WorkerPool）物理拆分；(2) 開機自癒自動回復殘留 `RUNNING` 任務；(3) 狀態單一真實來源（SSOT），禁止記憶體集合與 DB 狀態雙軌失步；(4) 外部 AI 產出未達品質門檻時入 `DATA_DIR/needs_review/` 並標 `NEEDS_REVIEW` 隔離 | 專案架構提煉（`worker_pool.py`, `ISSUE-002`, `ISSUE-035`, `ISSUE-038`） | 待決定 |
| 2026-11-22 | `[P1][無建置前端/離線]` Zero-Build Vanilla JS 前端三件套：(1) 輕量 `EventBus` + `StateStore` 解耦多腳本狀態同步；(2) `apiFetch` 包裝（GET 自動重試一次、寫入絕不自動重試、斷線友善提示條）；(3) UI 偏好存本機 SQLite 並開 HTTP/MCP 介面，`localStorage` 僅作首屏快取且伺服器回應前禁止回寫，圖示與字型內建 `static/vendor/` 離線可用 | 專案架構提煉（`studio-core.js`, `ADR-008`, `ADR-009`, `ISSUE-033`, `ISSUE-034`） | 已採用（v3.6.0 `web/api_client.js`） |
| 2026-11-22 | `[P2][展示部署]` 提供「單檔無後端互動 Demo 建置範本（`build_demo.py`）」：直接讀取真實生產前端內嵌成單一 `docs/demo/index.html`，搭配攔截 `window.fetch` 的 `demo-mock.js` 與虛擬資料，只維護一套 UI 即可部署 GitHub Pages 互動展示 | 專案架構提煉（`scripts/build_demo.py`, `scripts/demo/`） | 待決定 |

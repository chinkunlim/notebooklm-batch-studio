# SPEC-022：Gemini Notebook 登入與文獻瀏覽器改用真的 Chrome

- **狀態**：Draft <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-25
- **相關任務 / ADR**：TASK-042（決策 D3）／ISSUE-043／ADR-011（文獻下載不繞過機器人檢查）／ISSUE-053（Gemini 網頁版已改真 Chrome）

## 1. 目標

使用者回報兩個地方被擋（2026-11-25，D3）：

1. **Gemini Notebook 登入**：`notebooklm-batch-studio login --browser` 呼叫 notebooklm-py 的 `notebooklm login`，由 Playwright 開瀏覽器，Google 拒絕登入（「這個瀏覽器或應用程式可能不安全」）。
2. **文獻下載**：`adapters/literature/browser.py` 用 Playwright `launch_persistent_context(channel="chrome")` 開 Chrome；遇到 Cloudflare 機器人檢查時，使用者人工勾選後仍一直循環（ISSUE-043）。

兩者都改成和「Gemini 筆記」（`adapters/gemini/chrome_session.py`、`auth_runtime.py`）一樣的做法：**程式用一般方式啟動真的 Chrome（獨立資料夾、開除錯埠），使用者自己操作，程式之後才用 CDP 接上**。成功的樣子：

- 使用者在網頁或 CLI 按「登入 Gemini Notebook」→ 跳出真的 Chrome → 自己登入 Google → 程式偵測到登入、存下 `storage_state.json` → 「設計與自訂」的登入卡片顯示「就緒」，之後的佇列工作正常。
- 文獻下載遇到 Cloudflare 檢查時，使用者勾選一次就能通過（通常如此，但不保證所有網站都會放行）。

## 2. 使用情境

- **第一次使用或憑證過期**：使用者在「設計與自訂 → 登入狀態」看到 Gemini Notebook「已過期」，按「登入」，在跳出的 Chrome 裡自己登入。
- **下載文獻**：使用者在「文獻」頁按「下載」，跳出的 Chrome 開到出版社頁面；遇到 Cloudflare 或 OpenAthens 登入時自己完成，程式等待後繼續下載 PDF。
- **AI 工具**：Claude Code／Antigravity 透過 MCP 呼叫登入工具（需 `confirm=True`），由使用者在跳出的 Chrome 操作。

## 3. 需求

- **必須 (Must)**：
  1. **Gemini Notebook 登入改真 Chrome**：新增服務，以 `ChromeLaunch(chrome_path, user_data_dir, start_url="https://notebooklm.google.com/")` 啟動 Chrome（`ensure_chrome`），輪詢分頁網址；分頁到 `notebooklm.google.com` 且有有效的 Google 登入 cookie（重用 `auth_runtime._is_valid_auth_cookie` 的判斷）時，以 CDP 短暫連線，用 `context.storage_state(path=…)` 存到 notebooklm-py 使用的路徑（現行 `adapter.storage_path`），權限 600，然後斷線。
  2. 存完後用 notebooklm-py 做一次即時驗證（現行 `check_auth_status(live_check=True)`），失敗就回報「登入未完成」，不要覆蓋原本有效的檔案（先寫到暫存檔，驗證通過才取代）。
  3. 三個入口一起接（核心規則 13）：CLI `login --browser` 改走新流程；HTTP `POST /api/notebooklm/login`（新路由，回傳進度或結果）；MCP 工具 `notebooklm_login(timeout_seconds, confirm)`，`confirm=False` 時只回說明。網頁「設計與自訂 → 登入狀態」的 Gemini Notebook 卡片加「登入」按鈕。
  4. **文獻瀏覽器改真 Chrome**：`BrowserPublisherFetcher.__enter__` 改為 `ensure_chrome(ChromeLaunch(..., user_data_dir=chrome_user_data_dir(profile_dir), start_url="about:blank"))`＋`sync_playwright().chromium.connect_over_cdp(cdp_endpoint(port))`，使用 `browser.contexts[0]`；`__exit__` 只斷開 CDP 連線並依設定決定是否關閉 Chrome（預設關閉，與現在一致）。
  5. **沿用現有登入資料**：文獻瀏覽器現在的 Playwright 持久資料夾本身就是 Chrome 使用者資料夾；新做法直接指向同一個資料夾，使用者不用重新登入 OpenAthens（實作時實測確認；不行就在登入卡片提示重新登入一次）。
  6. **不繞過機器人檢查**（ADR-011）：遇到 Cloudflare／CAPTCHA 時維持現在的 `_needs_user` → 等使用者處理 → `wait_seconds` 逾時拋 `NeedsUserError` 的流程；程式不點、不填、不改瀏覽器指紋。
  7. **不處理密碼**：程式不輸入、不保存 Google 密碼（PROJECT_RULES §4）；OpenAthens 自動填入維持現有設定（預設關閉）。
  8. 路徑由 config 提供（`DATA_DIR/state/…`），不寫死；Chrome 路徑沿用 Gemini 筆記的設定值。
  9. 同一個使用者資料夾同時只能有一個 Chrome：重用 `ensure_chrome` 的「已在執行就沿用」與啟動鎖。
  10. 寫 ADR：Gemini Notebook 登入與文獻瀏覽器改用真 Chrome＋CDP，取代 Playwright 啟動的瀏覽器。
- **可選 (Nice to have)**：
  - 備案：notebooklm-py 的 `notebooklm login --browser-cookies chrome::<Profile>`（需 `uv add 'notebooklm-py[cookies]'`），直接讀已安裝 Chrome 的 cookie；放在「進階」選項，預設不用（會讀使用者主要 Chrome 的 cookie，範圍較大）。
  - Gemini Notebook 與 Gemini 筆記共用同一個 Chrome 資料夾（只登入一次）。見未決問題 1。
- **不做 (Out of scope)**：
  - 連到使用者平常用的 Chrome 主設定檔（Chrome 136 起不允許對預設資料夾開遠端除錯埠，且風險過大）。
  - 任何自動通過 Cloudflare／CAPTCHA 的方法。
  - 改動 notebooklm-py 套件本身。

## 4. 介面 / API

| 入口 | 輸入 | 輸出 | 錯誤 |
|---|---|---|---|
| CLI `uv run notebooklm-batch-studio login --browser` | — | 終端機顯示「已開啟 Chrome，請登入」→「登入完成」 | 逾時（預設 300 秒）exit 1、找不到 Chrome exit 2 |
| HTTP `POST /api/notebooklm/login` | `{"timeout_seconds": 300}` | `{"status": "signed_in" \| "timeout", "storage": "<相對 DATA_DIR 的路徑>"}` | 409 已有登入流程進行中；500 找不到 Chrome |
| MCP `notebooklm_login(timeout_seconds=300, confirm=False)` | 同上 | 同上（JSON 字串）；`confirm=False` 回說明 | 同上 |
| 文獻下載 | 不變 | 不變 | 不變（`NeedsUserError`、`SourceError`） |

回應不得包含 cookie 內容或完整的 `storage_state`。

## 5. 驗收標準

- [ ] Given 沒有有效憑證，When 執行登入並在（假的）CDP 端點回報 `notebooklm.google.com` 分頁與有效 cookie，Then 寫出 `storage_state.json`（權限 600）並回 `signed_in`。（單元測試，假 CDP）
- [ ] Given 登入逾時，When 時間到仍沒有登入分頁，Then 回 `timeout`，原本的 `storage_state.json` 內容不變。
- [ ] Given 新存的憑證即時驗證失敗，Then 不取代原檔、回報「登入未完成」。
- [ ] Given 已有登入流程進行中，When 再呼叫 HTTP 登入，Then 回 409。
- [ ] Given MCP `confirm=False`，Then 不啟動 Chrome，只回說明。
- [ ] Given 文獻瀏覽器啟動，Then 呼叫 `ensure_chrome` 與 `connect_over_cdp`，不再呼叫 `launch_persistent_context`。（單元測試，以假物件記錄呼叫）
- [ ] Given 遇到機器人檢查且 `wait_seconds=0`，Then 拋 `NeedsUserError`，程式沒有任何點擊或填寫。
- [ ] 實機（使用者）：真 Chrome 登入 Gemini Notebook 成功，佇列可跑一件工作；文獻下載遇 Cloudflare 時勾選一次即通過（記錄網站名稱與結果；不通過就更新 ISSUE-043）。
- [ ] `agentctl check` 0 警告；ADR 已寫；README 與 SPEC-003 的入口表已更新。

## 6. 未決問題

1. Gemini Notebook 與 Gemini 筆記要共用同一個 Chrome 資料夾嗎？共用只要登入一次，但兩個功能同時要用 Chrome 時會共用同一個視窗。建議共用。
2. CDP 接上的 Chrome 下載檔案的行為：`_download` 用 Playwright 的下載事件，接上既有 Chrome 時下載位置可能是 Chrome 預設的「下載」資料夾。實作第一步先做小實驗確認；必要時用 CDP `Browser.setDownloadBehavior` 指定到暫存資料夾。
3. 文獻下載完成後要不要保留 Chrome 開著（下次更快、也保留 Cloudflare 的通過狀態）？預設關閉，可設定。

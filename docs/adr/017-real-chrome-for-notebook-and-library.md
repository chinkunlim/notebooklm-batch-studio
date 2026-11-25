# ADR-017：Gemini Notebook 登入與文獻瀏覽器改用真的 Chrome（獨立資料夾＋CDP）

- **狀態**：Accepted <!-- Proposed | Accepted | Superseded by ADR-NNN -->
- **日期**：2026-11-25
- **Agent**：`claude-code`
- **任務**：`TASK-042`

## 1. 背景與問題

使用者回報（D3）：notebooklm-py 的 login 用 Playwright 開瀏覽器，Google 拒絕登入；文獻瀏覽器用 Playwright launch_persistent_context，遇到 Cloudflare 檢查時人工勾選仍一直循環（ISSUE-043）。Playwright 啟動的 Chrome 帶 --enable-automation，navigator.webdriver 為 true，會被當成自動化瀏覽器。Gemini 筆記已用真 Chrome＋CDP 解決同樣問題（ISSUE-053）。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. 維持 Playwright 啟動的瀏覽器 | 不用改 | Google 拒絕登入；Cloudflare 一直循環 |
| B. notebooklm-py `--browser-cookies chrome` | 不用 Playwright、套件內建 | 讀使用者主要 Chrome 的所有 cookie，範圍過大；需多裝套件；文獻瀏覽器仍無解 |
| C. 正常啟動真 Chrome（獨立資料夾）＋CDP 接上（採用） | 和 Gemini 筆記同一套、已驗證；不帶自動化參數 | 需管理 Chrome 程序；網站仍可能另外檢查 |
| D. 連到使用者平常用的 Chrome | 登入狀態現成 | Chrome 136 起不允許對預設資料夾開除錯埠；風險過大 |

## 3. 決策與理由

兩處都改用 chrome_session.ensure_chrome 正常啟動 Chrome（不帶任何自動化參數），Playwright 只用 connect_over_cdp 接上。Gemini Notebook 登入：獨立資料夾 DATA_DIR/state/notebooklm_chrome_profile，分頁到 notebook.google.com 且有 Google 登入 cookie 時存 storage_state 到暫存檔，讀一次用量表驗證通過才取代原檔（不覆蓋可用的登入）；CLI login --browser、HTTP POST /api/notebooklm/login、MCP notebooklm_login(confirm)、網頁登入卡片「登入」按鈕。文獻瀏覽器：沿用原本的資料夾（原本就是 Chrome 使用者資料夾，已登入的 OpenAthens 等保留），結束時關閉 Chrome。不採用 notebooklm-py 的 --browser-cookies（會讀使用者主要 Chrome 的 cookie，範圍過大）；不與 Gemini 筆記共用資料夾（筆記可能以無頭模式佔用同一個 Chrome，登入視窗會看不到）。

## 4. 影響與代價

仍不繞過任何機器人檢查（ADR-011）：使用者自己勾選，程式只等待。真 Chrome 通常能通過 Cloudflare，但不保證每個網站。用暫存資料夾實測：navigator.webdriver=false、CDP 連線與關閉正常。Google 實際登入與 Cloudflare 網站需使用者實機驗收（SPEC-026）。測試：tests/test_notebook_chrome_login.py、tests/test_literature_chrome_cdp.py。

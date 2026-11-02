# ADR-009：網頁偏好記錄在本機資料庫；圖示與字型內建、可下載 Google Fonts

- **狀態**：Accepted <!-- Proposed | Accepted | Superseded by ADR-NNN -->
- **日期**：2026-11-02
- **Agent**：`claude-code`
- **任務**：`TASK-011`

## 1. 背景與問題

v05 的「設計與自訂」偏好（配色、版面、欄寬、排序、頭像…）與學習小記憶（每講音檔位置、上次停在、先回想再看選項）只存在瀏覽器 localStorage，換瀏覽器就消失；圖示（unpkg 的 lucide）與 Noto 字型（Google Fonts）從網路載入，離線時圖示會缺。使用者要求：這是本機程式，偏好要能記錄；圖示與字型要離線可用，內建 Noto、可選 Mac 系統字型，並能自行下載免費的 Google Fonts 使用。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. 偏好存 SQLite（既有本機資料庫），網頁以伺服器為準、localStorage 當快取（採用） | 和其他學習紀錄同一處、可備份、MCP 可讀改、有 Alembic 遷移 | 需要一張新表與遷移 |
| B. 偏好存 DATA_DIR 下的 JSON 檔 | 不用遷移 | 要自己處理同時寫入與驗證，和其他資料分散 |
| C. 字型改用 Mac 系統字型、不內建 | repo 不變大 | 和核准的設計字型不同；使用者要求內建 Noto 並可選系統字型與下載字型 |

## 3. 決策與理由

1) 偏好存在既有的本機 SQLite（DATA_DIR）新表 ui_preferences（key、value 文字、updated_at），由 PreferencesService 驗證（key 1-120 個英數與 . _ : -、value ≤ 512 KB、≤ 2,000 筆）；HTTP GET/PUT /api/preferences、POST /api/preferences/reset；MCP get/set/reset_ui_preferences（改動要 confirm）。網頁以伺服器為準：啟動時先讀伺服器再套用；localStorage 只當首屏快取；變更 300 ms 合併送出、離開頁面時 keepalive 送完；伺服器還沒回應前不送任何變更，避免舊快取蓋掉紀錄；第一次（伺服器沒有資料）把這個瀏覽器原有的設定上傳。頭像照片縮成 256 px JPEG 再存。2) 圖示 lucide-static 0.460.0 與 @fontsource-variable/noto-sans-tc、noto-serif-tc 5.3.1 放進 static/vendor（照 pdf.js 的做法：暫存資料夾 pnpm add 後複製，附 LICENSE 與 README）；Noto 依 Unicode 範圍切成小檔，只載入畫面上的字。3) 設計與自訂新增「字型」：內文與標題各自選內建 Noto、Mac 的蘋方 / 宋體或已下載的 Google Fonts；下載由 adapters/fonts/google_fonts.py 呼叫 Google Fonts CSS2 API（8 個檔案同時下載，單一字族上限 60 MB），存到 DATA_DIR/fonts/<slug>/（font.css + woff2 + meta.json），由 /api/fonts/<slug>/<file> 提供；MCP list_fonts、install_google_font、delete_font（改動要 confirm）。

## 4. 影響與代價

正面：換瀏覽器、清快取、重開伺服器後設定都還在；Agent 也能透過 MCP 讀改；完全離線也能顯示圖示與字型；使用者可自選字型。代價：repo 多約 10 MB 字型檔（單檔都很小）；下載中文 Google Fonts 約需數秒到數十秒、約 5-10 MB 存在 DATA_DIR；偏好是整台電腦共用一份（沒有多使用者）。新增偏好時沿用 load/save（studio-shell.js），不要直接用 localStorage。

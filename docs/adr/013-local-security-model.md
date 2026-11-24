# ADR-013：本機安全模型：提示注入防線、瀏覽器設定檔與圖書館帳密

- **狀態**：Accepted <!-- Proposed | Accepted | Superseded by ADR-NNN -->
- **日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-028`

## 1. 背景與問題

專案整合 literature-fetch 與 note-studio 後，會把不可信文字（PDF、網路研究來源、文獻詮釋資料、Gemini 回覆）送進網頁與 MCP，並以 Chrome 遠端除錯埠操作已登入 Google 的設定檔、以 .env 的圖書館帳密自動登入 OpenAthens。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A：逐點防禦（跳脫、scheme 白名單、CSP、confirm、路徑白名單、700 權限）| 改動小、不影響既有介面與 inline handler；每條防線都有測試 | XSS 主要依賴跳脫正確；CSP 仍需 'unsafe-inline' |
| B：全面改寫（移除所有 inline handler 改 addEventListener、嚴格 CSP nonce、HTTP 加 token 驗證）| 防線最完整 | 需改寫 200+ 個 inline handler 與所有呼叫端（Open WebUI、MCP 客戶端）設定，風險與工作量大 |
| C：維持現狀 | 無工作量 | 已確認的路徑穿越與 XSS 無法接受 |

## 3. 決策與理由

採方案 A；B 列為後續可選的強化。

1) 所有 AI/來源文字一律當資料：HTML 跳脫（含雙引號與單引號）、jsAttr、連結 scheme 白名單（safeHttpUrl 與 markdown_fragment）、CSP；MCP 會改資料的工具一律要求 confirm=True，未確認時統一回傳 `{"confirmed": false, "warning": "..."}`。2) 呼叫端路徑只能落在 DATA_DIR、STUDY_ROOT_DIR、課程登錄的 source_dir，或舊筆記匯入白名單 LEGACY_NOTE_STUDIO_DIR（domain/path_safety）。3) 瀏覽器設定檔資料夾建立為 700（adapters/private_dir）。4) Chrome 遠端除錯埠只綁 127.0.0.1（Chrome 預設），接受本機其他程式可連線的風險，不另做驗證。5) 圖書館帳密只讀 .env 的 LIBRARY_EMAIL / LIBRARY_PASSWORD（舊名 USER_* 仍相容），僅用於 OpenAthens，絕不存放 Google 密碼；學校網域與 EBSCO profile 不再寫死在程式碼。

## 4. 影響與代價

inline script 仍需 'unsafe-inline'，XSS 主要靠跳脫；之後若移除 inline handler 可收緊 script-src。本機其他使用者帳號無法讀取瀏覽器 cookie，但同帳號的其他程式仍能連 Chrome 除錯埠。

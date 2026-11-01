# ADR-002：以 session storage_state 驗證取代 .env 明文帳密

- **狀態**：Accepted
- **日期**：2026-11-01
- **Agent**：`antigravity`
- **任務**：`TASK-007`

## 1. 背景與問題

NotebookLM 需要 Google 帳號授權以讀取個人筆記本並調用生成功能。使用者詢問：
「如果登入的 session 用不到，需要手動登入，我需要有一個 `.env` 檔案儲存 username 和 password，是 OK 的嗎？」

需要評估在系統中以 `.env` 存放 Google 帳號密碼並自動登入的可行性與安全性風險。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. 在 `.env` 存放明文帳號與密碼，自動啟動無頭瀏覽器模擬登入 | 設定看似直覺，使用者只需輸入帳密 | **極度危險且技術上不可行**：Google 登入機制具備嚴密反機器人檢測、圖形驗證碼 (CAPTCHA)、手機推播或 2FA (二步驟驗證) 與通行密鑰 (Passkey)。明文密碼容易洩漏，且自動化程式碼幾乎 100% 會被 Google 阻擋登入或導致帳號被鎖。 |
| B. 採用 CLI 互動式手動登入 (`notebooklm-py` / Playwright) 產生 `storage_state.json` (Cookie/Token)，存於安全路徑 | 100% 相容 Google 2FA/Passkey，符合核心原則 5（秘密不進程式碼）；不存密碼，僅存 session cookies，過期後重新登入即可 | 初次使用需要打開瀏覽器視窗登入一次，無法做到完全無頭的「零人工初次登入」。 |

## 3. 決策與理由

選擇 **方案 B**：嚴格禁止在 `.env` 或任何程式碼中存放 Google 帳號與密碼。

1. **安全性原則**：Google 帳號涉及使用者完整個資與資安風險，絕不能在本機以明文儲存主密碼。
2. **實務可靠性**：Google 登入流程具備硬體金鑰、TOTP、手機簡訊與風險偵測，僅能由使用者於互動視窗中完成。
3. **隔離保存**：登入完成後所取得的 Cookie 與 Session State 存於 `$HOME/.config/notebooklm-batch-studio/profiles/default/storage_state.json`（檔案權限 600），過期時由系統發出提示導引使用者重新執行 `notebooklm login`。

## 4. 影響與代價

- **正面影響**：徹底杜絕 Google 主密碼外洩風險，並相容各種雙因素驗證。
- **代價**：當 Google Cookie 失效或過期（通常數週或數月），使用者需再次透過互動登入更新 session state。
- **後續注意**：Web UI 與 CLI 的 `check_auth_status` 會主動檢查 `storage_state.json` 是否存在，若缺少則於儀表板醒目提示登入指引。

# ADR-001：以 notebooklm-py 為主、Playwright 補位操作 NotebookLM

- **狀態**：Accepted <!-- Proposed | Accepted | Superseded by ADR-NNN -->
- **日期**：2026-10-21
- **Agent**：`claude-code`
- **任務**：`-`

## 1. 背景與問題

NotebookLM 沒有給一般 Pro 帳號用的官方 API，需要自動建立 notebook、上傳、逐份來源生成與下載。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. NotebookLM Enterprise 官方 API | 官方、穩定 | 需要 Google Cloud 企業版，使用者是個人 Pro 帳號，不適用 |
| B. 只用 Playwright 模擬操作網頁 | 網頁能做的都能做（勾選來源、改名、讀 quiz 畫面） | 慢；Google 改版面就容易壞 |
| C. 只用 notebooklm-py（非官方，走網頁內部呼叫） | 快；README 宣稱支援 audio、quiz、infographic、mind map、flashcards 與匯出 | 非官方，Google 改內部格式會壞；可能有做不到的步驟 |
| D. C 為主，C 做不到的步驟用 B 補 | 兼顧速度與覆蓋率 | 要維護兩套操作方式 |

## 3. 決策與理由

採用 **D**。notebooklm-py 處理大部分步驟；只勾選單一來源、改名、取出 quiz / mind map 內容等若 notebooklm-py 做不到，改用 Playwright。
兩者都放在 `adapters/` 層，對上層提供同一組介面，換實作不影響 services。

登入：使用者在程式開啟的瀏覽器中**親自登入一次**，程式只沿用登入狀態（存放在 `~/.config/notebooklm-batch-studio/`，權限 600），
程式不輸入、不保存 Google 密碼。

## 4. 影響與代價

- 兩種方式都是非官方，Google 改版時可能失效；轉換層與 adapter 要有離線測試（用存下來的範例資料），失效時只改 adapter。
- 使用非官方方式可能不符合 Google 服務條款，由使用者自行承擔；建議控制頻率、遵守每日上限，不用多帳號繞過。
- 實作第一個任務是技術驗證（SPEC-002 §3），結果寫回下方。

## 5. 技術驗證結果

（待實作時填寫：每項「可行／不可行＋方法」、每日上限、生成時間。）

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

## 5. 技術驗證結果（於 2026-10-22 實測驗證完成）

以 1 份 2 頁生物學講義（`sample_cell_biology.pdf`）與測試 Notebook 進行實測，結果如下：

| 驗證項目 | 實測結果 | 耗時 | 說明與呼叫方法 |
|---|---|---|---|
| 1. 單一來源勾選 | ✅ 可行 | ~4.2s (上傳與解析) | `client.sources.add_file` 取得 `source_id`，各生成方法原生支援 `source_ids=[source_id]` |
| 2. Quiz 完整擷取 | ✅ 可行 | 55.4s (10 題) | `generate_quiz` + `download_quiz` 產出 JSON，包含完整題幹、4 選項、`isCorrect` 標記、各選項詳解 `rationale` 與 `hint` |
| 3. Flashcards 擷取 | ✅ 可行 | 66.1s (50 張) | `generate_flashcards` + `download_flashcards` 產出 JSON，包含完整 `front` 與 `back` |
| 4. Mind map 階層樹 | ✅ 可行 | 10.4s | `generate_mind_map` + `download_mind_map` 產出完整多層階層樹 JSON（`name` 與 `children` 結構） |
| 5. 產出更名 | ✅ 可行 | ~1.0s | `client.artifacts.rename(nb_id, artifact_id, "[03] Quiz 1-基礎")` 成功在 NotebookLM 內更名 |
| 6. 憑證隔離保存 | ✅ 可行 | - | 透過 `NOTEBOOKLM_HOME=~/.config/notebooklm-batch-studio` 實現完全隔離，不觸碰使用者密碼 |

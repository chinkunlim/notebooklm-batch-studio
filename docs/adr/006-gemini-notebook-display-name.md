# ADR-006：產品改名 Gemini Notebook：只改顯示名稱，不改程式識別名稱

- **狀態**：Accepted
- **日期**：2026-11-01
- **Agent**：`claude-code`

## 1. 背景與問題

Google 在 2026-07-16 把 NotebookLM 改名為 Gemini Notebook，網址也改成 `notebook.google.com`；舊網址會自動轉址。使用者要求整個程式改用新名稱，上網查資料時也用新名稱搜尋。

程式裡的「NotebookLM」有兩種：
- **給人看的文字**：網頁、使用說明、log、錯誤訊息、MCP 工具描述、文件。
- **程式識別名稱**：上游套件 `notebooklm-py`（import 名稱 `notebooklm`）、本專案的套件 `notebooklm_batch_studio`、`adapters/notebooklm/`、API 路徑 `/api/notebooklm/quota`、資料夾名稱、MCP server 名稱。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. 只改給人看的文字和連結 | 使用者看到的全是新名稱，不破壞任何相容性 | 程式碼裡仍有 `notebooklm` 這種小寫的識別名稱 |
| B. 連識別名稱一起改 | 名稱完全一致 | 上游套件名稱改不了；改 API 路徑、MCP server 名稱、資料夾名稱，會讓 Open WebUI、Claude Code 等既有連線全部失效 |

## 3. 決策與理由

選 A。
- 文字裡完整的單字 `NotebookLM` 一律改成 `Gemini Notebook`。
- 產品名稱統一為「Gemini Notebook 學習工作室」。
- 連到筆記本的網址改用 `https://notebook.google.com/notebook/<id>`。
- 使用說明保留一句「Gemini Notebook 就是原本的 NotebookLM」，讓使用者知道兩者是同一個服務。
- 過去的 ADR、known-issue 和 CHANGELOG 是歷史紀錄，維持當時的寫法，不回頭修改。

## 4. 後果

- `tests/test_rename.py` 會檢查：網頁和說明文字沒有舊名稱、筆記本連結使用新網域。
- 上游的 `notebooklm-py` 照常使用，它內部呼叫的端點不受影響。
- 之後上網查資料時，以「Gemini Notebook」為主要關鍵字；需要找舊文章時，再加上「NotebookLM」一起搜尋。

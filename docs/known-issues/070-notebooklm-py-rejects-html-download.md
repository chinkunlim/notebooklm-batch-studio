# ISSUE-070：notebooklm-py 下載器把 HTML 產出誤判為登入頁而拒絕下載

- **狀態**：🟡 已規避 (Mitigated)
- **發現日期**：2026-11-25
- **Agent**：`claude-code`
- **任務**：`TASK-040`

## 1. 現象

Gemini Notebook 的學習網頁（「make me a site」產生，Studio 類型代碼 `10`，檔案 `text/html`）用 notebooklm-py 的下載功能取回時一律失敗。

- **錯誤訊息**：`ArtifactDownloadError: Download failed: received HTML instead of media file. Authentication may have expired. Run 'notebooklm login'.`
- **重現步驟**：2026-11-25 以唯讀方式掃描「函數與圖形」筆記本，取得類型 `10` 那筆 Studio 原始列（`row[24] = [檔名.html, "text/html", 檢視網址, 下載網址, …]`），交給 notebooklm-py 的 `download_url` 下載。
- **影響範圍**：所有 HTML 類產出（SPEC-021 的學習網頁、整本書學習網頁）。其他產出（語音、圖片、PDF）不受影響。登入其實沒有過期，錯誤訊息會誤導使用者重新登入。

## 2. 根本原因

notebooklm-py 0.8.6 的 `notebooklm/_artifact/downloads.py` 裡，`_reject_html_download()` 只要回應的 `content-type` 含 `text/html` 就丟出錯誤。它假設下載的一定是媒體檔，收到 HTML 只可能是 Google 登入頁；這個假設在 Gemini Notebook 推出網頁產出（2026-11-16）後不再成立。兩條下載路徑（curl_cffi 與 httpx 串流）都會呼叫它，而且是程式庫內部函式，沒有參數可以關掉。

## 3. 修正或規避方式

不改第三方套件，由本專案自行下載（SPEC-021 Task 3，`adapters/notebooklm` 內實作）：

- 用 notebooklm-py 的 `storage_state` 中的 Google cookie 發出 GET。
- 只允許連到 `*.google.com`／`*.googleusercontent.com`，跳轉也要檢查主機。
- 下載內容若是 Google 登入頁（而不是學習網頁），才當成登入過期並拒絕存檔。

2026-11-25 已用這個方式在真實資料上取回 127 KB（函數與圖形）與 137 KB（生涯諮商與實務第 1 講）的網頁。實作完成後在相關程式碼加註 `Refs: ISSUE-070`，狀態保持「已規避」，直到 notebooklm-py 原生支援 HTML 產出。

## 4. 防回歸

SPEC-021 Task 3 的測試（`tests/test_learning_site.py`）要涵蓋：正常 HTML 會存檔、登入頁 HTML 被拒絕、非 Google 主機（含跳轉）被拒絕。升級 notebooklm-py 前先跑這些測試，並檢查 `_reject_html_download` 是否已改變行為。

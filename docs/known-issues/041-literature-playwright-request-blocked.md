# ISSUE-041：Playwright context.request 下載 PDF 被出版社防護擋下 (403)

- **狀態**：🟢 已根治 (Resolved)
- **來源**：整合自 `literature-fetch`（原 `ISSUE-001`，2026-10-20）
- **任務**：`TASK-025`

## 1. 現象

用 `page.context.request.get()` 下載 Sage / NEJM / T&F 的 PDF 一律回 403 或 HTML 驗證頁，即使頁面本身已正常載入。

- **錯誤訊息**：`pdf request attempt=1 status=403 bytes=5815 url=https://journals.sagepub.com/doi/pdf/10.1177/1754073917742706`（內容是 "Just a moment..." 驗證頁）
- **影響範圍**：Sage、NEJM AI、Wiley、T&F 等有 Cloudflare 防護的出版社。

## 2. 根本原因

`APIRequestContext` 是在瀏覽器之外由 Playwright 送出的請求，連線指紋與真實 Chrome 不同；頁面導覽本身為真實 Chrome，故不受影響。

## 3. 修正或規避方式

改為在頁面內執行 `fetch(url, {credentials: 'include'})` 並以 base64 傳回（`adapters/literature/browser.py::BrowserPublisherFetcher._fetch_in_page`）；Wiley 的 `/doi/pdf/` 閱讀頁改為 `/doi/pdfdirect/...?download=true`（`pdf_url_variants`）。

## 4. 防回歸

`tests/literature/test_literature.py::BrowserHelpersTest`。

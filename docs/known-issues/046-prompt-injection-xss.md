# ISSUE-046：提示注入可經 Markdown `javascript:` 連結與 onclick 參數觸發 XSS

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-028`

## 1. 現象

惡意 PDF 或網路研究來源可誘導 Gemini 輸出 `[x](javascript:...)`，報告/家教回覆渲染成可點擊的 `javascript:` 連結；前端 59 處 `onclick="fn('${escHtml(x)}')"` 中 AI 產生的標籤或標題含單引號即可跳出 JS 字串；notes-gen 的 option 與章節按鈕未跳脫。網頁與 API 同源，XSS 可呼叫所有 API。

- **錯誤訊息**：無（`markdown_fragment('[x](javascript:alert(1))')` 輸出 `<a href="javascript:alert(1)">`）
- **重現步驟**：讓 Gemini 回覆含 `[點我](javascript:fetch('/api/courses/X',{method:'DELETE'}))` 的報告或家教訊息，在研讀工作室點擊連結；或 QA 筆記標籤含 `x');alert(1);('`。
- **影響範圍**：研讀工作室所有顯示 AI 產出（報告、家教、QA 筆記標籤、遠端筆記本標題、檔名）的地方；XSS 與 API 同源，可刪課程、上傳檔案。

## 2. 根本原因

markdown_fragment 只跳脫原始 HTML，未過濾連結 scheme；escHtml 不處理引號，而瀏覽器會先解碼屬性實體再執行 inline handler；沒有 Content-Security-Policy。

## 3. 修正或規避方式

report_converter 只保留 http/https/mailto/相對連結；新增 studio-escape.js 的 jsAttr()（JSON 字串再 HTML 跳脫）取代所有 inline handler 參數；notes-gen 補 escHtml；新增 SecurityHeadersMiddleware（CSP：connect-src 'self'、object-src 'none'、base-uri 'none'、frame-ancestors 'self'，以及 nosniff、no-referrer）。inline script 仍需 'unsafe-inline'，跳脫是主要防線。（相關程式碼註解加 `Refs: ISSUE-046`）

## 4. 防回歸

tests/test_security_hardening.py::XssAndHeaderTests；瀏覽器實測 onclick 參數為 JSON 字串且點擊無錯誤。

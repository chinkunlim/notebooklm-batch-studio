# ADR-016：學習網頁以沙箱 CSP 檢視，進度經 postMessage 存回研讀工作室

- **狀態**：Accepted <!-- Proposed | Accepted | Superseded by ADR-NNN -->
- **日期**：2026-11-25
- **Agent**：`claude-code`
- **任務**：`TASK-040`（SPEC-021）

## 1. 背景與問題

學習網頁是 Gemini Notebook 產生、含 JavaScript 的 HTML（SPEC-021）。依 ADR-013，Gemini 的回覆一律當不可信資料；來源 PDF 裡的提示詞注入有可能讓產生的網頁帶有惡意程式。網頁又要求「作答與進度用 localStorage 保存」。

原計畫只在本站網址下附嚴格 CSP（`connect-src 'none'`）開啟。實作時發現漏洞：CSP 只限制網頁自己的請求；同源網頁可以 `window.open('/')` 開出本站另一頁並直接操作它（同源可互相存取 DOM），再透過那一頁呼叫本站 API（例如刪除課程）。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. 本站網址＋嚴格 CSP（原計畫） | 簡單；網頁的 localStorage 原生可用 | 可經 `window.open` 或 `parent` 取得同源頁面，繞過 CSP 呼叫 API |
| B. CSP `sandbox`（不透明來源）＋記憶體儲存 | 網頁碰不到本站任何頁面與 API；實作最少 | 重新開啟網頁後作答進度消失 |
| C. CSP `sandbox`＋注入儲存轉接器，進度經 `postMessage` 存回研讀工作室（採用） | 隔離同 B；在研讀工作室開啟時進度可保存 | 多一段注入程式；直接用新分頁開啟時進度只保留到關閉 |
| D. 另開一個埠號／網域專門服務網頁 | 真正不同來源，localStorage 原生可用 | 要多跑一個伺服器、登記埠號、處理啟動與 Host 檢查，維運成本高 |

## 3. 決策與理由

採用 **C**（使用者 2026-11-25 選定「Isolate + keep progress」）。

- 網頁只經 `GET /api/artifacts/{code}/site/{path}` 提供，CSP 為：`default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'; sandbox allow-scripts allow-modals allow-downloads`（沒有 `allow-same-origin`、`allow-popups`）。
- 一般下載路由對 `learning_site*`／`course_learning_site*` 一律以附件下載，不在本站來源直接顯示。
- 伺服器在 `<head>` 之後注入 `static/site-storage-shim.js`：以記憶體實作 `localStorage`／`sessionStorage`，從 iframe 網址的 `#nbs-site=<json>` 片段讀入已存進度（片段不會送到伺服器，讀完立即移除；Chromium 進入不透明來源時會清空 `window.name`，所以不用 `name`），每次變更以 `postMessage` 通知父頁。
- 研讀工作室（`studio-site-viewer.js`）的 iframe 也加 `sandbox` 屬性；只接受 `event.source` 等於該 iframe 的訊息，值必須都是字串、總長 ≤ 2 MB，存到自己的 localStorage `nbsSite:<code>/<path>`。

## 4. 影響與代價

- 2026-11-25 用無頭 Chromium 驗證：網頁內 `fetch('/api/status')` 被 `connect-src` 擋下、`window.open('/')` 被沙箱擋下、存取 `parent.document` 拋出 `SecurityError`；在研讀工作室重新載入後進度延續（1 → 2）。
- 「新分頁開啟」的網頁進度只保存到分頁關閉，介面上已標示。
- 網頁若用 `localStorage.foo = x` 這種屬性寫法（而非 `setItem`），不會被保存。
- Claude 桌面 App 內建瀏覽器面板會以 `ERR_BLOCKED_BY_CLIENT` 擋下這個 iframe（同樣的標頭在獨立測試頁可正常嵌入），屬該面板限制；使用者平常用的 Chrome 不受影響。
- 測試：`tests/test_learning_site.py::ViewTest`。

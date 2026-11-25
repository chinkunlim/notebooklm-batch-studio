# SPEC-021：學習網頁產出（每講／整本書，經 Gemini Notebook 對話產生、從 Studio 取回）

- **狀態**：Implemented <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-25
- **相關任務 / ADR**：TASK-040、ADR-016（學習網頁以沙箱 CSP 檢視）、ISSUE-070（notebooklm-py 拒絕 HTML 下載）、提示詞 `assets/prompts/notebook_site/learning_site.md`

## 1. 目標

使用者定案（2026-11-25）：測驗、閃卡之外，每一講與整本書都要能產生**互動＋視覺化的學習網頁**，跟其他產出一樣排進佇列、額度用完自動續跑、存進課程資料夾、在研讀工作室開啟。

已實測（生涯諮商與實務第 1 講）：

- notebooklm-py 0.8.6 沒有產生網頁的 API；但用 `chat.ask(notebook_id, prompt, source_ids=[…])` 送出以 `make me a site` 開頭的提示詞，Gemini Notebook 會回覆「已送出生成請求」，並在 Studio 新增一筆項目。
- 該項目：類型代碼 `10`（函式庫歸為 `FILE`），狀態 `2`（生成中）→ `3`（完成），約 11 分鐘；原始資料 `row[24] = [檔名.html, "text/html", 檢視網址, 下載網址, …, [_, 提示詞]]`，`row[15]` 為建立時間。
- 下載網址在 `contribution.usercontent.google.com`，需帶登入 cookie；notebooklm-py 的下載器會把 HTML 回應誤判為登入頁而拒絕，必須自行下載。
- 下載得到 137 KB、完全自足（無外部資源）的 HTML，含滑桿、測驗、導覽模式。

## 2. 使用情境

- 在課程的產出選擇中勾選「學習網頁」（每講）或「整本書學習網頁」（整門課），排入佇列後自動產生並下載到 `03 Notes/NotebookLM/<講次>/learning_site.html`（整門課為 `_course_synthesis/course_learning_site.html`）。
- 在研讀工作室點「學習網頁」，於新分頁安全地開啟。
- 「重新生成」產生 `learning_site_v2.html`，舊版保留。

## 3. 需求

- **必須 (Must)**：
  1. 新產出類型 `learning_site`（中文「學習網頁」）與 `course_learning_site`（「整本書學習網頁」），檔名 `learning_site.html`／`course_learning_site.html`（重新生成加 `_vN`）。不加入任何既有 profile 的預設清單（使用者自行勾選）。
  2. 提示詞由 `assets/prompts/notebook_site/learning_site.md` 的 A（每講）或 B（整本書）段落產生，填入課程名稱、講次、章名、讀者、課程範圍；工作若有自訂提示詞且以 `make me a site` 開頭則原樣使用，否則把自訂內容附在末尾「補充要求」。
  3. 產生流程：記下送出前 Studio 既有的網頁 id → 以該講（或全部）來源送出提示詞 → 等待新出現的類型 10、`text/html` 項目完成 → 下載。同一本筆記本一次只跑一個網頁工作，避免把別人的網頁當成自己的。
  4. 等待規則：送出後 5 分鐘內沒有出現新項目 → 若 Gemini 回覆含額度相關字詞則視為額度用完（`QuotaExceededError`，交給既有的等待額度機制），否則失敗並記錄回覆內容；出現後最多再等 30 分鐘；項目狀態為失敗時直接失敗。
  5. 下載：只連 Google 網域（`*.google.com`、`*.googleusercontent.com`），跟隨最多 6 次轉址；回應是 Google 登入頁時視為登入過期；內容必須是 HTML 才寫入，原子寫入。
  6. 額度：產生前依用量表的 `canvas` 項目預檢。
  7. **安全檢視**：學習網頁是 Gemini 產生的不可信 HTML，只能經 `GET /api/artifacts/{code}/site/{path}` 開啟，回應附嚴格 CSP（禁止任何網路請求、表單送出與外部資源）並以 CSP `sandbox` 給予不透明來源，網頁無法經 `window.open`／`parent` 碰到本站頁面；下載路由對學習網頁一律以附件下載，不在本站來源直接執行。作答進度由注入的儲存轉接器經 `postMessage` 存回研讀工作室（ADR-016，2026-11-25 使用者定案）。
  8. 研讀工作室新增「學習網頁」入口；課程產出選擇清單出現兩個新類型；「從既有檔案建立產出紀錄」能認得 `learning_site*.html`。
  9. 不改既有 MCP／HTTP 工具介面：課程產出類型、重新生成等既有入口自動支援新類型。
- **不做 (Out of scope)**：同步 Gemini Notebook 網頁上手動做的網頁（`sync_service`）；把網頁加入預設 profile；改寫或修正網頁內容。

## 4. 介面 / API

- `GET /api/artifacts/{code}/site/{file_path}` → `text/html`，標頭 `Content-Security-Policy: default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'; sandbox allow-scripts allow-modals allow-downloads`，另附 `X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`、`Cache-Control: no-store`；`<head>` 後注入 `static/site-storage-shim.js`；非 `.html` 回 415。

## 5. 驗收標準

見實作計畫 `docs/superpowers/plans/2026-11-25-learning-site-artifacts.md` 各任務的測試（`tests/test_learning_site.py`，24 項）。

- [x] 型別、命名、額度項目 `canvas`、網頁選項（Task 1）
- [x] 提示詞 A／B 版、自訂提示詞規則、排程不帶通用提示詞（Task 2）
- [x] Studio 原始列解析、只連 Google 的下載、登入頁判定、原子寫入、每本筆記本一把鎖（Task 3）
- [x] 送出 → 等新網頁 → 等完成 → 下載；額度／失敗對應；`ArtifactRunner` 分派且不改名（Task 4）
- [x] 沙箱路由、下載一律附件、研讀工作室「學習網頁」入口；無頭 Chromium 驗證 fetch／popup／parent 皆被擋、進度重新載入後延續（Task 5）
- [x] 真實資料：生涯諮商與實務第 1 講排一個學習網頁工作（2026-11-25 使用者同意；21:12 開始、21:28 完成，一次成功，存成 `learning_site.html`，214 KB，標題「生涯諮商：生命生涯發展觀點（Ch01 互動學習講義）」；經沙箱路由開啟無主控台錯誤，側欄導覽與進度條可用。這份網頁沒有用 localStorage，所以沒有作答進度可保存）
- [ ] 真實資料：整本書版（B）跑一次（需使用者同意，會用到額度）

## 6. 未決問題

- Gemini 產生網頁的實際額度上限未公布（用量表項目為 `canvas`）。
- Google 若改變 Studio 原始資料格式（`row[24]` 位置），解析會失效；以 fixture 測試鎖住並在失敗時記錄原始資料。

# ISSUE-040：UI/UX: Topbar alignment, native select styling, nav/cram toggles, auto-keypoints/bookmarks/zoom-presets, and right-column collapse

- **狀態**：🟢 已解決 (Resolved)
- **發現日期**：2026-11-14
- **Agent**：`antigravity`
- **任務**：`-`

## 1. 現象（對應第二批 5 張截圖）

1. **圖 1 — 寬度對齊與頂部按鈕外觀一致化**：
   - 「考前急救包」（`#cramPanel`）與下方「講義與學習產出物」（`#bench`）寬度不一致，`#cramPanel` 的寬度才是正確的。
   - 頂部離開全螢幕 Icon 按鈕的高度需與「💬 探索提問 ⌘J」一致，且「💬 探索提問 ⌘J」的高度、膠囊圓角與造型應比照左側課程選擇按鈕（`.course-pill`）。
2. **圖 2 — 講次下拉選單視覺風格不一致**：
   - `#studyLectureSelect` 使用瀏覽器原生 `<select>` 深灰系統彈窗，與整體米色／森林綠溫潤紙感（Editorial / Warm Paper）風格落差過大，應改為自訂風格化 Popover / Dropdown 選單。
3. **圖 3 — 上/下一講按鈕辨識度 ＋ 「🔥 考前急救」Toggle 狀態回饋**：
   - 「上一講 (`‹`)」與「下一講 (`›`)」按鈕過小不明顯，應改為兩個**高對比圓形 Icon 按鈕**（與背景明顯區隔）。
   - 「🔥 考前急救」按鈕本身可再次點擊退出，但目前開關狀態缺少明顯配色區分與 on/off 切換動畫，使用者難以察覺可再次點擊關閉。
4. **圖 4 — PDF 自動重點、閱讀進度續讀、書籤與三段式縮放框**：
   - 講義重點應**自動**產生（進入講義若無重點即自動觸發，無須手動點「產生重點」）。
   - 需記錄使用者最後閱讀頁數／捲動位置並提供「跳至上次閱讀位置」，且支援新增／跳轉 **Bookmarks（書籤）**；相關按鈕整合排列於「新分頁開啟」同排工具列。
   - 縮放百分比數字（如 `200%`）需加上外框、水平居中並與左右放大鏡保持等距；點擊百分比框可依**目前可視 PDF 容器寬度**自動切換 **大（200% Max）/ 中（(Min+Max)/2）/ 小（125% Min）** 三種預設比例。
5. **圖 5 — 全版型講義區捲動停靠 ＋ 右側欄位與各區塊獨立收合**：
   - 無論在「主舞台」、「雙欄」、「上下」三種模式，向下捲動時皆須於「講義」區塊頂部乾淨停靠（`scroll-margin-top` / sticky 對齊）。
   - 雙欄模式下，右側欄的「收合 / 展開」按鈕應常駐顯示於**右側欄頂部/右上角**（而非僅在滑鼠移到兩欄分隔線才出現；分隔線仍保留拖曳調寬與收合按鈕）。
   - 右側欄位內的每一個獨立區塊（如「語音摘要」、「學習產出物」、「本講重點」）也都要能各自**上下收合 / 展開（collapse / expand）**。
6. **圖 6（補充）— 研讀右上工具列高度不一致與按鈕群組整合**：
   - `專注 25:00` 計時器按鈕高度與旁邊切換列不同，且目前 `專注 25:00`、`主舞台 / 雙欄 / 上下`、`課程目錄 / 研讀` 分散為三個獨立膠囊，應整合為同一組等高一體化控制列（以細分隔線區分機能）。
7. **圖 7（補充）— 點擊頂部課程選擇膠囊時出現整塊藍色反白（Text Selection Highlight）**：
   - 點擊頂欄 `#coursePickBtn` 展開 `#coursePop` 課程選單時，選單內文字會被意外選取成整塊藍色反白。

- **影響範圍**：`index.html`、`studio.css`、`studio-start.js`、`studio-cram.js`、`studio-learning.js`、`studio-reader.js`

## 2. 根本原因

1. `#cramPanel` 與 `#bench` 所在容器寬度規則不同；`.focus-exit` 與 `#qaDrawerToggle` 未共用 `.course-pill` 膠囊高度規範。
2. `#studyLectureSelect` 直接使用原生 `<select>`，在 macOS/Safari/Chrome 上會渲染系統預設深色選單。
3. `#studyPrevLecBtn` / `#studyNextLecBtn` 僅使用 `.btn-ghost.btn-sm` 淡字元；`#cramModeBtn` 缺少獨立 `.is-active` 雙態視覺與微動畫。
4. `studio-reader.js` 目前只在 `loadKeyPoints` 渲染手動按鈕、尚未自動觸發生成、未持久化 `last_position` 與 `bookmarks`、縮放標籤為純 `<span>` 不可點擊切換三段比例。
5. 雙欄模式的收合把手（`.col-toggle`）僅掛在 `.gutter` 分隔線上且預設透明/hover 才出現；右側各 `.card` 缺少獨立折疊標題列與收合狀態。
6. `.subbar` 右側將 `#btnPomodoro`（`.btn.btn-ghost.pomodoro`）與兩個 `.seg` 各自獨立擺放，padding 與高度規則不同，未統一整合在同一個膠囊容器內。
7. `studio.css:879` 的 `.cp-btn` 與 `.cp-pop` 未設定 `user-select: none; -webkit-user-select: none;`，導致點擊/連點展開選單時觸發瀏覽器原生文字選取反白。

## 3. 修正或規避方式

待實作（預計與 `ISSUE-039` 一併規劃並逐項修復，完成後標註 `Refs: ISSUE-039, ISSUE-040`）。

## 4. 防回歸

待補：靜態資源檢查（`test_button_routes.py`、`test_rename.py`）與 `docs/demo/index.html` 重建驗證。

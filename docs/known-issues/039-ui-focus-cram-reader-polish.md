# ISSUE-039：UI/UX: Focus mode sidebar & exit icon, cram panel spacing/exit, PDF reader auto-fit/margin comments/scroll-stop

- **狀態**：🟢 已解決 (Resolved)
- **發現日期**：2026-11-14
- **Agent**：`antigravity`
- **任務**：`-`

## 1. 現象（對應 5 張截圖）

1. **圖 1 — 全螢幕／專注模式側邊欄與按鈕重疊**：進入專注全螢幕後，左側 Dock 永久隱藏（無法滑鼠靠左呼出）；右上角「離開專注」按鈕重疊蓋住「探索提問」按鈕。
2. **圖 2 — 考前急救模式切換與版面間距**：
   - 進入「🔥 考前急救」後缺乏明顯關閉按鈕與離開切換，難以回到正常研讀介面。
   - 區塊標題應標示為「🔥 考前急救包」，且目前與下方「講義與學習產出物」卡片黏在一起、缺乏間距。
3. **圖 3 — PDF 閱讀器寬度、重點批註與使用者自訂 Highlight**：
   - PDF 預設 `125%`（最大 `200%`）相較外框過小、無法依容器寬度自動適配（Fit-to-Width），且使用者無法拖動調整閱讀區大小。
   - 左側重點筆記固定在頂部空白處，未採用類似電子書 / Word 的**行邊批註（Margin Comments）**設計（隨 PDF 捲動到該頁才顯示、可展開/收合）。
   - 目前僅有系統標註的 3 種高亮（必考核心、重要概念、補充），缺少第 4 種**使用者自訂 Highlight ＋ 個人備註**。
4. **圖 4 vs 圖 5 — 捲動卡點裁切頂部工具列**：在講義區向下捲動時，卡片/工具列會停在半截位置（圖 4 頂部工具列被裁切，對比圖 5 完整顯示），需調整 `scroll-margin-top` / sticky 停靠位置。
5. **圖 5 — 離開全螢幕按鈕改為純 Icon**：目前右上/左上離開按鈕為文字「離開專注」，應改置於左上角並沿用與全螢幕按鈕同一套 Lucide icon 設計（如 `icon-minimize-2` / `icon-shrink`），不顯示文字。

- **影響範圍**：`index.html`、`studio.css`、`studio-start.js`、`studio-cram.js`、`studio-reader.js`

## 2. 根本原因

1. `studio.css:735` 在 `.app.focus` 直接 `display: none` 隱藏 `.dock`，未實作左緣 hover / `mousemove` 滑出抽屜；`.btn.focus-exit` 固定於 `top: var(--s4); right: var(--s4)`，與頂欄「探索提問」重疊。
2. `#cramPanel`（`index.html:233`）缺少獨立關閉按鈕與 `margin-bottom`，標題為「考前急救面板（臨時抱佛腳）」。
3. `studio-reader.js:12` 將預設 `scale` 寫死 `1.25` 且未依 `.reader-pages` 容器寬度計算 Fit-to-Width，亦無拖曳調整寬度、依頁同步顯示的 Margin Comments 及文字選取自訂 Highlight/Comment 持久化。
4. 講義區塊捲動停靠與 sticky header 高度未配合頂部留白（`scroll-margin-top`）。
5. `index.html:616` 使用純文字 `<button ... id="focusExit">離開專注</button>`，未套用 Lucide icon 樣式。

## 3. 修正或規避方式

已於 commit `5d69525` 一併修復並同步更新 `docs/demo/index.html`（`Refs: ISSUE-039, ISSUE-040`）：
1. 專注模式實作左側邊緣 hover／滑動呼出 `.dock` 抽屜，將 `#focusExit` 移至左上角並改為純 Lucide icon，避免與右側「探索提問」按鈕重疊。
2. `#cramPanel` 標題調整為「🔥 考前急救包」，加入明確關閉按鈕與下方卡片間距。
3. 實作 PDF 閱讀器依 `.reader-pages` 容器寬度自動適配（Fit-to-Width）、可拖曳寬度、隨捲動頁面同步展開/收合的行邊批註（`studio-reader-notes.js`），以及第 4 種使用者自訂 Highlight 與個人備忘持久化。
4. 配合頂部留白調整講義區塊 `scroll-margin-top` 與 sticky 停靠位置，防止捲動裁切頂部工具列。

## 4. 防回歸

已通過靜態資源與路由檢查（`tests/test_button_routes.py`、`tests/test_rename.py`）以及全套 220 項離線單元／整合測試，並同步透過 `scripts/demo/build_demo.py` 更新靜態展示檔。

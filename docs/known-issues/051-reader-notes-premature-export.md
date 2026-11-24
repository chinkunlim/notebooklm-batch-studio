# ISSUE-051：studio-reader-notes.js 載入時 ReferenceError

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-028`

## 1. 現象

每次開頁 console 出現 hookPdfSelectionHighlight is not defined，reader-notes 的 window 匯出被中斷。

- **錯誤訊息**：`Uncaught ReferenceError: hookPdfSelectionHighlight is not defined at studio-reader-notes.js:455`
- **重現步驟**：開啟網頁（任何頁面），看瀏覽器 console。
- **影響範圍**：reader-notes 的 window 匯出物件建立失敗（函式本身仍是全域，但每次載入都有錯誤）。

## 2. 根本原因

reader-notes 把 studio-pencil.js 才定義的 hookPdfSelectionHighlight 放進自己的匯出物件，而 pencil 較晚載入。

## 3. 修正或規避方式

移除該匯出（函式本來就是 pencil.js 的全域函式）。（相關程式碼註解加 `Refs: ISSUE-051`）

## 4. 防回歸

瀏覽器實測重新載入後無 console 錯誤、window.toggleReaderBookmark 為 function。

# ISSUE-031：Safari 捲到底時側欄下方露出一段

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-02
- **Agent**：`claude-code`
- **任務**：`TASK-011`

## 1. 現象

在 Safari 捲到頁面底部，左側側欄沒有延伸到視窗底，下方露出一段頁面背景；Chrome 正常。

- **錯誤訊息**：沒有錯誤訊息（畫面問題）
- **重現步驟**：用 Safari 開 http://127.0.0.1:8768 →「設計與自訂」→ 捲到底，側欄下方出現一段淺色背景
- **影響範圍**：所有頁面的側欄（桌面寬度，Safari）

## 2. 根本原因

側欄是 position: sticky，高度寫成 100vh / 100dvh。Safari 對 vh 的計算和實際可見範圍不同，側欄比視窗短；先前用背景色填補只是遮掩。

## 3. 修正或規避方式

側欄改成 position: fixed; top: 0; bottom: 0（由瀏覽器依實際視窗決定長度），版面保留同寬的空欄；拿掉背景填補；html/body 關閉回彈捲動。（相關程式碼註解加 `Refs: ISSUE-031`）

## 4. 防回歸

用 Playwright 的 Chromium 與 WebKit 在頁首、頁中、頁尾量側欄的 top / bottom 必須等於 0 / innerHeight；全高元素不要用 vh 搭配 sticky。

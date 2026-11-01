# ISSUE-029：固定面板（sticky）不會固定：body 的 overflow-x: hidden

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

課件頁左側的重點清單設成 `position: sticky`，但捲動時仍然跟著頁面跑掉，無法邊看重點邊捲動課件。

- **影響範圍**：`static/studio.css` 的全域「不要水平捲軸」規則

## 2. 根本原因

為了避免水平捲軸，之前在 `html, body` 設了 `overflow-x: hidden`。CSS 規定 overflow 只要有一軸不是 visible，另一軸就會變成 auto。結果 body 自己變成捲動容器，sticky 元素改成相對 body 固定，而不是相對視窗，所以失效。

## 3. 修正方式

改用 `overflow-x: clip`：一樣不會出現水平捲軸，但不會產生捲動容器，sticky 恢復正常。已在 1280 與 375 寬度實測：沒有水平捲軸，清單也會固定。

## 4. 防回歸

`studio.css` 在這條規則旁加了註解。之後若有人想改回 `hidden`，看到註解就知道會出問題。

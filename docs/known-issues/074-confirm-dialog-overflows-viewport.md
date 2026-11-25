# ISSUE-074：確認對話框內容太長時按鈕跑出畫面，無法繼續操作

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-25
- **Agent**：`claude-code`
- **任務**：`SPEC-020`

## 1. 現象

2026-11-25 使用者切割心理學研究法整本課本，按「預覽並切割」後確認框列出 17 章，「取消／切割 11 章」按鈕超出畫面底部，對話框不能捲動，畫面被遮罩擋住無法操作。

- **錯誤訊息**：無（畫面卡住，主控台沒有錯誤）
- **重現步驟**：批次排程 → 心理學研究法「偵測到課本」卡片 → 預覽並切割（17 章清單）
- **影響範圍**：所有用 askConfirm／選擇框且內容很長的操作（課本切割、搬移講義等）；資料未受影響（沒有送出請求）

## 2. 根本原因

studio.css 的 #confirmBox／#pickBox 只限寬度（max-width 460px），沒有限制高度；#confirmText 也沒有 overflow，內容一長整個框超出視窗。

## 3. 修正或規避方式

#confirmBox／#pickBox 加 max-height: calc(100dvh - 32px) 與直向 flex；#confirmText／#pickText 加 overflow-y: auto、min-height: 0；按鈕列 flex-shrink: 0。內容在框內捲動，按鈕固定可見。瀏覽器驗證 30 行內容：視窗 798px，確認按鈕底部 758px 可見、文字區可捲動。（相關程式碼註解加 `Refs: ISSUE-074`）

## 4. 防回歸

tests/test_confirm_dialog_scroll.py

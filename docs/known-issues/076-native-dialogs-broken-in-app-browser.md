# ISSUE-076：網頁用瀏覽器內建 prompt／confirm／alert，在 App 內建瀏覽器中失效

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-26
- **Agent**：`claude-code`
- **任務**：`TASK-036`

## 1. 現象

2026-11-26 實測 TASK-036 #21 時發現：「修改課程名稱…」按了沒反應。Claude 桌面 App 的內建瀏覽器對 prompt() 直接拋錯（prompt() is not supported）、confirm() 一律回傳取消、alert() 不顯示。共 38 處：課程改名、改代碼、變更產出模式、手動登錄、新增資料夾、PDF 標記備註、文獻重新辨識／移除、產生既有產出紀錄、Studio 遠端產出（自訂報告、電影感影片、投影片微調、匯出 Google 文件、加入網址／純文字來源、網路研究）等，在 App 內全部無法使用；錯誤訊息（alert）也看不到。

- **錯誤訊息**：`Error: prompt() is not supported.`（主控台，studio-library.js:186 openCourseDisplayNameFlow）；confirm() 靜默回傳 false
- **重現步驟**：在 Claude 桌面 App 的內建瀏覽器開網頁 → 批次排程 → 任一課程「進階工具 → 修改課程名稱…」→ 沒有任何反應
- **影響範圍**：App 內建瀏覽器使用者：38 處操作無法使用、錯誤看不到；使用者平常的 Chrome 不受影響。資料未受影響（操作根本沒送出）

## 2. 根本原因

前端早期直接用 window.prompt / window.confirm / alert；後來雖有 askConfirm／askPick 頁內對話框，舊呼叫沒有全部換掉。使用者平常的 Chrome 能用，所以沒被發現。

## 3. 修正或規避方式

新增頁內文字對話框 askText（studio-pickers.js，套用 .modal 樣式、Enter 確認、Esc／點背景取消並經 MODAL_CLOSERS 回傳 null）；prompt → askText（要選的改成 askPick 下拉：產出模式、研究模式、產出類型、建議報告、講次範圍），confirm → askConfirm，alert → showToast。（相關程式碼註解加 `Refs: ISSUE-076`）

## 4. 防回歸

tests/test_no_native_dialogs.py（掃描全部 static/*.js，禁止 prompt/confirm/alert）

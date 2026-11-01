# ISSUE-019：「加入後立即開始」取消勾選無效

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

加入課程時取消勾選「加入後立即開始」，工作仍然馬上開始生成，使用者來不及先調整設定。

- **錯誤訊息**：無
- **重現步驟**：web 服務開著（AUTO_START_QUEUE=true），取消勾選後加入課程
- **影響範圍**：`entrypoints/static/index.html` `confirmAddFolders`、佇列認領

## 2. 根本原因

勾選框只決定要不要「另外呼叫一次啟動佇列」；佇列在 web 啟動時已自動運作，新加入的工作一進佇列就被認領。

## 3. 修正或規避方式

新增課程層級的暫停（`courses.paused`，migration `d21a28b5d5a0`）：暫停的課程工作不會被認領、也不算在「還有工作要跑」裡。
取消勾選＝以暫停狀態加入；課程頁有「▶️ 開始生成／⏸ 暫停這門課」。加入時帶的進階設定在任何工作開始前就先寫入。

## 4. 防回歸

`tests/test_course_admin.py`：`test_paused_course_jobs_are_not_claimed_until_started`。

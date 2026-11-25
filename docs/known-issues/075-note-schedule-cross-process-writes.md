# ISSUE-075：筆記排程被網頁和 MCP 同時寫入時會遺失項目或寫入失敗

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-26
- **Agent**：`claude-code`
- **任務**：`SPEC-025 R1`

## 1. 現象

網頁伺服器和 MCP 伺服器是不同的程式，各自讀、改、寫 DATA_DIR/state/note_schedule.json。2026-11-26 用兩個程式各加入 60 章重現：最後只保留 61／120 筆，另有 24 次加入失敗（FileNotFoundError）。

- **錯誤訊息**：`FileNotFoundError`（os.replace 找不到 `.note_schedule.json.tmp`）；遺失項目則沒有任何訊息
- **重現步驟**：兩個程式（spawn）各建一個 `NoteScheduler` 指向同一檔案，同時對不同課程各呼叫 60 次 `enqueue_course` → 檔案只剩 61 筆
- **影響範圍**：網頁與 MCP（Claude Code、Antigravity）同時加入、暫停、恢復或清除筆記排程時；實際使用中機率低，但一旦發生排程項目會無聲遺失。使用者資料未受影響（沒有發生過）

## 2. 根本原因

NoteScheduler 只用 threading.Lock，只在同一個程式內有效；兩個程式的「讀→改→寫」交錯時，後寫的覆蓋先寫的。兩者也共用同一個暫存檔名 .note_schedule.json.tmp，一方 os.replace 後另一方找不到暫存檔。

## 3. 修正或規避方式

NoteScheduler._locked 在 threading.Lock 之外加 fcntl.flock 檔案鎖（note_schedule.json.lock），讀與寫都在鎖內；鎖超過 10 秒拿不到就拋 ScheduleBusyError，網頁回 503「筆記排程忙碌中，請稍後再試」。重跑重現腳本：120／120、無錯誤。（相關程式碼註解加 `Refs: ISSUE-075`）

## 4. 防回歸

tests/test_note_schedule_file_lock.py（兩個程式各寫 60 筆、鎖逾時、HTTP 503）

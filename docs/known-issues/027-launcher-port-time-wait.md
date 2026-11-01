# ISSUE-027：啟動器誤判埠號被佔用（剛停止的伺服器留下 TIME_WAIT）

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

先停掉 8768 的伺服器，再雙擊「Gemini Notebook 學習工作室.app」，結果伺服器沒有啟動，log 寫「埠號 8768 已被 未知的程式 使用」。但 `lsof` 查不到任何程式在監聽這個埠號。

- **影響範圍**：`entrypoints/port_check.py`、`scripts/launch_app.sh`

## 2. 根本原因

新加的啟動前檢查用一個沒有設定 `SO_REUSEADDR` 的 socket 試著 bind。伺服器剛停止時，它留下的連線還在 `TIME_WAIT` 狀態，沒有這個選項的 bind 就會失敗。

uvicorn 本身有設定 `SO_REUSEADDR`，可以正常啟動，所以這是檢查本身的誤判。

## 3. 修正方式

`port_is_free()` 改成和 uvicorn 一樣先 `setsockopt(SO_REUSEADDR)` 再 bind：
- 只是 `TIME_WAIT` 的埠號算作可用。
- 真的有程式在監聽時仍然會失敗，並列出是哪個程式。

測試在 Linux CI 的另一個細節，見 ISSUE-025。

## 4. 防回歸

`tests/test_port_check.py` 的 `test_recently_closed_port_is_free`：拿掉修正時這個測試會失敗，已實際確認。

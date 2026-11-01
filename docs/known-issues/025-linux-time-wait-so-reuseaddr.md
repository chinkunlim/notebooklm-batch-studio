# ISSUE-025：Linux TCP 要求 TIME_WAIT 前後 socket 皆啟用 SO_REUSEADDR 否則 bind 失敗

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`antigravity`
- **任務**：`-`

## 1. 現象

GitHub Actions CI (Ubuntu 24.04 Linux) 執行 `test_recently_closed_port_is_free` 失敗，而 macOS 本機測試全數通過：

- **錯誤訊息**：
  ```text
  FAIL: test_recently_closed_port_is_free (test_port_check.PortCheckTest.test_recently_closed_port_is_free)
  AssertionError: False is not true
  ```
- **重現步驟**：在 Linux 環境執行 `uv run python -m unittest tests/test_port_check.py`。
- **影響範圍**：GitHub Actions CI 測試流程失敗，無法自動驗收推送。

## 2. 根本原因

在 Linux 網路協定棧中，`SO_REUSEADDR` 允許重用處於 `TIME_WAIT` 狀態的通訊埠的先決條件是：**所有曾綁定該位址/埠號的 socket（包含進入 TIME_WAIT 的連線 socket）在當初 `bind()` 前都必須有開啟 `SO_REUSEADDR`**。
在 macOS (BSD) 網路堆疊中，只要後續嘗試 bind 的新 socket 帶有 `SO_REUSEADDR`，即可重用 `TIME_WAIT` 的 port。
先前測試案例在建立模擬伺服器時漏掉了 `server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)`，導致其接受連線後產生的 `TIME_WAIT` socket 在 Linux 下被視為不允許重用。

## 3. 修正或規避方式

在 `tests/test_port_check.py` 的 `test_recently_closed_port_is_free` 中，替模擬伺服端 socket 在 bind 前加上 `server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)`，忠實模擬真實伺服端（如 uvicorn）的 bind 行為。

## 4. 防回歸

`tests/test_port_check.py::PortCheckTest::test_recently_closed_port_is_free` 在 Linux (CI) 與 macOS 環境下皆能穩定通過。

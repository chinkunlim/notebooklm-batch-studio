# ISSUE-028：更新後瀏覽器仍使用舊的 CSS／JS

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

改了 `static/studio.css` 並重新整理後，頁面仍套用舊規則。在瀏覽器裡讀取 `document.styleSheets`，看到的是舊的 `overflow-x: hidden`。使用者的 Chrome App 視窗更新後也可能維持舊外觀。

- **影響範圍**：`entrypoints/api.py` 的 `/static` 掛載

## 2. 根本原因

FastAPI 的 `StaticFiles` 只送 ETag 和 Last-Modified，沒有送 `Cache-Control`。瀏覽器會依「啟發式快取」直接使用舊檔，不回伺服器確認。

## 3. 修正方式

新增 `NoCacheStaticFiles`，每個靜態檔都加上 `Cache-Control: no-cache`。瀏覽器每次都會回伺服器確認；檔案沒變時伺服器只回 304，成本很低。

已經快取舊檔的瀏覽器，需要按一次 ⌘⇧R 強制重新整理。

## 4. 防回歸

`tests/test_button_routes.py` 的 `test_static_files_are_revalidated`。

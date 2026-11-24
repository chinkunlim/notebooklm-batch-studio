# ISSUE-049：空 Host 標頭可通過檢查、artifact 的 code 可為 ..

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-028`

## 1. 現象

HostValidationMiddleware 對空 Host 直接放行；/api/artifacts/{code}/download 未驗證 code，code=.. 可讀到其他課程的產出。

- **錯誤訊息**：無（空 Host 回 200；`/api/artifacts/%2E%2E/download/OTHER/x.md` 回其他課程檔案）
- **重現步驟**：`curl -H 'Host:' http://127.0.0.1:8768/api/courses`；或下載 artifact 時把 code 設成 `..`。
- **影響範圍**：DNS rebinding 防線的邊界情況；同一個 output 目錄下的其他課程產出。

## 2. 根本原因

條件寫成 if host_header and ...；_resolve_artifact_path 只檢查 file_path 不檢查 code。

## 3. 修正或規避方式

空 Host 一律 400；code 先經 validate_path_segment，不合法回 404。中介層移到 entrypoints/http_middleware.py。（相關程式碼註解加 `Refs: ISSUE-049`）

## 4. 防回歸

tests/test_security_hardening.py::test_csp_and_empty_host、test_artifact_download_rejects_parent_course_code。

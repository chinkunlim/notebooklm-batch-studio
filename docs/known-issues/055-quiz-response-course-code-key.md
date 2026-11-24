# ISSUE-055：測驗 API 回傳欄位名稱打錯成 course.code

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-029`

## 1. 現象

GET /api/courses/{code}/lectures/{no}/quiz/{variant} 與 MCP get_quiz 回傳 {"course.code": ...}，其他 API 都用 course_code；以欄位名稱取值的 Agent / Open WebUI 讀不到課程代號。實機 115-1 L1 quiz 回應可見此鍵。

- **錯誤訊息**：無（回應 JSON 含 `course.code`）
- **重現步驟**：`GET /api/courses/115-1/lectures/1/quiz/1`
- **影響範圍**：讀取測驗的 HTTP 與 MCP 呼叫端；網頁未使用此欄位。

## 2. 根本原因

services/quiz_reader.py 組回傳字典時把屬性存取 course.code 誤寫成字串鍵。

## 3. 修正或規避方式

改為 course_code。（相關程式碼註解加 `Refs: ISSUE-055`）

## 4. 防回歸

tests/test_api_and_mcp.py::test_quiz_and_artifact_download 斷言 course_code 存在、course.code 不存在。

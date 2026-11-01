# ISSUE-014：網頁勾選的產出內容沒有存進資料庫

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 現象

在網頁「加入課程」時勾選要的產出，第一次會照勾選生成；之後課程被重新註冊（再跑 batch、watcher 偵測到新 PDF）就改用 profile 的預設組合。

- **錯誤訊息**：無（靜默）
- **重現步驟**：網頁只勾資訊圖表加入課程 → 放入新 PDF 讓 watcher 觸發 → 新講次產生的是 full profile 的工作
- **影響範圍**：`adapters/db/models.py`、`adapters/db/repository.py`

## 2. 根本原因

`Course.selected_chapter_artifacts` / `selected_course_artifacts` 只存在 domain 物件，`courses` 資料表沒有對應欄位。

## 3. 修正或規避方式

`courses` 新增兩個 JSON 欄位（migration `d0a82d2914ab`）。`save_course` 只在收到非空的勾選時更新，重新掃描（沒有勾選資訊）不會清掉原本的選擇。

## 4. 防回歸

`tests/test_guides_and_reports.py`：`test_selection_is_kept_when_rescan_has_none`。

# ISSUE-071：Gemini Notebook 把學習網頁的改名當成檔名

- **狀態**：🟡 已規避 (Mitigated)
- **發現日期**：2026-11-25
- **Agent**：`claude-code`
- **任務**：`TASK-040`

## 1. 現象

用 artifacts.rename 把學習網頁（Studio 類型 10）改成「[Ch01] Learning Site」後，Studio 的標題與檔名都變成「[Ch01]_Learning_Site.html」：空白換成底線、補上 .html。2026-11-25 在生涯諮商第 1 講的網頁（3ee25a8f）實測；改名後下載內容與改名前逐位元組相同。

- **錯誤訊息**：無（改名成功，只是格式不同）。改名前 `title: [115-1] 生涯諮商`，改名後 `title: [Ch01]_Learning_Site.html | file: [Ch01]_Learning_Site.html`
- **重現步驟**：對類型 10 的 Studio 項目呼叫 `client.artifacts.rename(nb, id, "[Ch01] Learning Site")`，再用 `client.artifacts._list_raw(nb)` 讀回 row[1] 與 row[24][0]
- **影響範圍**：只影響 Studio 上學習網頁的顯示名稱；下載網址與內容不變，本機檔名不變

## 2. 根本原因

學習網頁在 Studio 以 HTML 檔呈現，Gemini Notebook 似乎以檔名當顯示標題；改名請求會同時改寫 row[1] 標題與 row[24][0] 檔名，並把標題整理成合法檔名。這是 Gemini 端行為，不是本專案能控制的。

## 3. 修正或規避方式

接受此行為：學習網頁照其他產出一樣改名（ArtifactRunner.rename_after_generation），Studio 顯示為「[Ch01]_Learning_Site.html」，前綴與其他產出一致可排序。本機檔名不受影響（learning_site.html）。（相關程式碼註解加 `Refs: ISSUE-071`）

## 4. 防回歸

tests/test_learning_site.py::RunnerTest::test_artifact_runner_dispatches_and_renames

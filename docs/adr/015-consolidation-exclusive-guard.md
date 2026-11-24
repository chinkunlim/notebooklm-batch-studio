# ADR-015：整併工具 --apply 獨占防護：要求停止伺服器並暫停資料夾監看器

- **狀態**：Accepted <!-- Proposed | Accepted | Superseded by ADR-NNN -->
- **日期**：2026-11-25
- **Agent**：`antigravity`
- **任務**：`TASK-035`

## 1. 背景與問題

consolidate --apply 會同時搬移 study 資料夾、合併分類目錄並重寫資料庫路徑，若與運行中的本機 Web 伺服器背景佇列或 CourseWatcher 同時進行將產生競態條件。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A：只靠 OS 檔案鎖 (`RunLock`) | 不影響伺服器執行 | 若 `watch` 守護或 Web 伺服器背景佇列仍在執行，搬移 `study/` 期間會誤觸 PDF 掃描或寫入 SQLite 造成競態 |
| B：要求停止 Web 伺服器＋跨行程鎖＋監看器暫停旗標（採行） | `--apply` 期間磁碟與資料庫完全靜止，安全且可逆 | 執行 `--apply` 前須先停止運作中的本機 Web 伺服器 |

## 3. 決策與理由

採用雙層獨占防護：(1) 檢查 config.http_host:config.http_port，若本機伺服器運行中則拒絕 --apply；(2) 取得 DATA_DIR/state/consolidate.lock 並寫入暫存旗標 DATA_DIR/state/consolidate.pause（finally 清除），CoursePdfEventHandler 偵測到該旗標即略過事件；同時檢查進行中佇列任務與文獻鎖。

## 4. 影響與代價

確保資料整併在完全靜止的檔案與資料庫狀態下執行，無需修改或破壞既有的 watch 守護流程；整併前須先關閉本機 Web 伺服器。

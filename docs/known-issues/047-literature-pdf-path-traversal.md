# ISSUE-047：文獻 PDF 檔名可指向文獻資料夾外的檔案

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-24
- **Agent**：`claude-code`
- **任務**：`TASK-028`

## 1. 現象

/api/literature/{key}/pdf 的備援路徑 literature_dir / item.file 沒檢查是否仍在資料夾內；legacy literature.db 的 file 欄位若為 ../x，伺服器會回傳任意檔案，匯入時也會從舊資料夾外複製檔案。

- **錯誤訊息**：無（回傳 200 與資料夾外的檔案內容）
- **重現步驟**：在舊 literature.db 放一筆 `file='../secret.pdf'` 後匯入，再 GET `/api/literature/<key>/pdf`。
- **影響範圍**：文獻 PDF 預覽與舊資料匯入；可讀取或複製 DATA_DIR 內文獻資料夾以外的檔案。

## 2. 根本原因

resolve_pdf_path 只對第一個候選路徑做 is_relative_to；legacy_import 直接信任舊 DB 的檔名。

## 3. 修正或規避方式

LiteratureManagerBase.resolve_pdf_path 對兩個候選資料夾都做 is_relative_to；legacy_import.safe_pdf_name 只接受不含資料夾的 .pdf 檔名。（相關程式碼註解加 `Refs: ISSUE-047`）

## 4. 防回歸

tests/test_security_hardening.py::LiteratureHardeningTests（fallback 與 legacy 匯入兩案例）。

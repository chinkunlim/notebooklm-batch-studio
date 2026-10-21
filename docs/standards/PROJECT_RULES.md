# 本專案專屬規則 (PROJECT_RULES)

> 規則分兩層：`docs/standards/` 的其他文件是**所有專案通用**的規範（由專案模板提供，`agentctl update` 會更新）；
> 本檔是**只適用這個專案**的規則，由這個專案自己維護，模板更新時不會被覆蓋。每次開工都要讀。

## 1. 領域知識與術語

- **課程**：一個 PDF 資料夾 = 一門課 = 一本 Gemini Notebook（NotebookLM），notebook 名稱 = 資料夾名稱。
- **講次**：課程中的一份 PDF，依檔名排序編號 `01, 02, …`。
- **產出**：audio、quiz（×3：1 基礎、2 理解、3 模擬考）、infographic、mind map、flashcards、study guide；整門課另有模擬考與全課程 mind map。
- **產出組合（profile）**：`full`、`quiz-only`、`exam-prep`，見 SPEC-001。

## 2. 本專案特有的規則

- **埠號**：`HTTP_PORT=8767`（8080 Open WebUI、8765 literature-fetch、8766 母版網頁、11434 Ollama、7456 Open Design 已占用）。
- **命名**：下載檔 `<課程代號>_<講次>_<主題>_<類型>[-序號]`，例如 `BIO101_03_細胞膜_Quiz2-理解.md`；放在 `DATA_DIR/courses/<課程代號>/<講次>_<主題>/`。NotebookLM 內只加 `[講次]` 前綴。
- **每份 PDF 單獨生成**：生成每講產出時只勾選該份 PDF；整門課產出才勾選全部。
- **操作 NotebookLM 只在 `adapters/`**：notebooklm-py 為主、Playwright 補位（ADR-001）。
- **遵守每日上限**：碰到上限就等隔天，不用多帳號繞過。

## 3. 和通用規範不同的例外（要寫理由）

- （目前沒有）

## 4. 禁止事項

- 不修改、不搬移使用者課程資料夾中的 PDF（只讀）。
- 程式不輸入、不保存 Google 密碼；登入由使用者在瀏覽器親自完成。
- 不自動刪除 NotebookLM 上的 notebook 或產出。

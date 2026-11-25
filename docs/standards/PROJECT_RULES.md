# 本專案專屬規則 (PROJECT_RULES)

> 規則分兩層：`docs/standards/` 的其他文件是**所有專案通用**的規範（由專案模板提供，`agentctl update` 會更新）；
> 本檔是**只適用這個專案**的規則，由這個專案自己維護，模板更新時不會被覆蓋。每次開工都要讀。

## 1. 領域知識與術語

- **課程**：`DATA_DIR/study/<學期>/<課程資料夾>`（例 `115-1/CP__30000-團體諮商`）對應一門課與一本 Gemini Notebook；課程代碼為 `<學期>_<課號>`（例 `115-1_CP30000`），筆記本標題為 `[<課號>] <課名> (<學期>)`。
- **分類與講次**：標準五分類為 `01 Materials`（課本與文獻）、`02 Handouts`（老師教材）、`03 Notes`（AI 筆記與個人隨筆）、`04 Homework`（作業）、`05 Assignments`（報告），可用 `.env` 的 `STUDY_CATEGORIES` 自訂；讀取相容 `01 Material`/`02 Handout` 別名。**講次來源**：`02 Handouts`（含子資料夾）內的 PDF 為講次；`02 Handouts` 沒有 PDF 時，改用 `01 Materials/<課本名>/` 中有 `.textbook.json` 標記的課本章節（SPEC-018），講次編號取自檔名 `ChNN`／`NN_`；`01 Materials` 預設不上傳（僅勾選「課本作為整門課來源」時納入）。
- **未歸檔區 (`scratch/`)**：`DATA_DIR/scratch/<種類>/`（`literature`、`notes`、`outputs`、`uploads`、`unarchived`）集中存放未歸檔或撤銷歸檔的檔案。
- **產出**：audio (`.m4a`)、quiz（×3：1 基礎、2 理解、3 模擬考，各 30 題）、infographic、mind map、flashcards、study guide、concept explanation report、學習網頁（`learning_site.html`，經 Gemini Notebook 對話產生，SPEC-021）；整門課另有模擬考、全課程 mind map 與整本書學習網頁（`course_learning_site.html`）。學習網頁只經沙箱路由 `/api/artifacts/{code}/site/…` 開啟（ADR-016）。
- **產出組合（profile）**：`full`、`quiz-only`、`exam-prep`（見 SPEC-001）以及不排程生成的 `record-only`（過去學期只登錄建立學習紀錄；可透過 SPEC-015 `adopt_existing_outputs` 將既有的 `03 Notes/NotebookLM/` 檔納管為 `done` 工作，且禁止對無筆記本的 `record-only` 課程觸發 `regenerate`，ISSUE-068）。可於 Web 介面自由切換個別項目開關。
- **版本化重新生成**：重新生成時不覆蓋舊檔案，Gemini Notebook 遠端標題後綴 `(v2)`，本機檔名後綴 `_v2`（歷史紀錄於 `job_versions`）。
- **多裝置資訊圖表**：資訊圖表預設為直式，並由 `image_fitter` 同步輸出 A4 PDF、iPad Air 4 (2360x1640) 與 MacBook Pro 14 吋 (3024x1964) 規格。
- **學生研讀工作台 (Study Portal)**：整合線上互動測驗、作答記錄 (`quiz_attempts`)、錯題本 (`quiz_mistakes`)、3D 閃卡、語音播放與 Anki CSV 間隔重複匯出。
- **研讀計畫與間隔複習 (SPEC-007)**：每日「Today」學習任務排程、考前倒數天數動態調整、跨講混合複習、測驗題目之 Gemini Notebook AI 詳解快取 (`explanations`)。
- **學習心理學與智慧閱讀 (SPEC-008)**：講義 PDF.js 離線閱讀器、Gemini Notebook 核心重點萃取與引文畫線定位、艾賓浩斯半衰期記憶強度計算（連續天數與掌握度熱圖）、作答信心評分（sure-but-wrong 認知盲點強烈警示）、蘇格拉底式引導家教 (`tutor_messages`)、25 分鐘番茄鐘專注計時。
- **單一產出獨立設定 (SPEC-006)**：支援個別產出覆寫題目數（預設 30 題）、難度、語言、資訊圖表方向與風格、投影片格式（PDF/PPTX），採「全域預設 ➔ 課程設定 ➔ 講次覆寫」三層繼承。
- **研讀工作室與外觀自訂 (SPEC-009，已實作 v05，ADR-008 / ADR-009)**：左側圖示側欄五頁（研讀總覽、研讀工作室、弱點複習、學習紀錄、批次排程），側欄底部是使用方法、專注模式、設計與自訂；唱盤播放該講真實語音摘要（黑膠 / 弦波 / 環形 / 聲譜，播放中離開研讀工作室會縮到側欄成迷你播放器）；工作台把講義與各產出物、AI 家教放在同一處，三種版面、四種排列、可調欄寬；五組配色＋日光 / 暗夜 / 自動、字型與頭像偏好保存於本機 SQLite `ui_preferences`（`/api/preferences`，ADR-009）。介面原型歸檔於 `docs/design/`，`version_05_claude_template.html` 是目前介面的設計依據。

## 2. 本專案特有的規則

- **埠號**：正式 `HTTP_PORT=8768`；開發驗證 8769、隔離測試 8770。全機埠號以 `~/Desktop/projects/00 init_dev_env/PORTS.md` 為準，用新埠號前先查表並更新。啟動時若 8768 已被其他程式佔用，伺服器會在 log 中列出是哪個程式並停止。
- **命名與位置**：課程資料位於 `DATA_DIR/study/<學期>/<課程資料夾>/`（`01 Materials`..`05 Assignments`），未歸檔檔案位於 `DATA_DIR/scratch/<種類>/`；NotebookLM 產出檔 `<課程代號>_<講次>_<主題>_<類型>[-序號][_vN]`（例如 `115-1_CP30000_03_細胞膜_Quiz2-理解.md`）存放在 `<study_dir>/03 Notes/NotebookLM/<講次>_<主題>/`，NoteStudio 筆記在 `<study_dir>/03 Notes/NoteStudio/`，問答筆記在 `<study_dir>/03 Notes/QA_Notes/`（`03 Notes` 其餘個人隨筆不動）；上傳的自訂來源存 `<study_dir>/02 Handouts/_uploaded/`（無 `study_dir` 時存 `scratch/uploads/<課程代號>/`）；不足 30 題之待審查項目放 `DATA_DIR/needs_review/`。Gemini Notebook 內只加 `[講次]` 前綴。
- **每份 PDF 單獨生成**：生成每講產出時只勾選該份 PDF（`source_ids=[source_id]`）；整門課產出才勾選全部。
- **保持來源 ID**：重新掃描註冊課程時，講義未變更者必須保留原有 `source_id`，禁止重複上傳至遠端筆記本。
- **操作 Gemini Notebook 只在 `adapters/`**：notebooklm-py 為主、Playwright 補位（ADR-001），語系代碼指定 `zh_Hant`，語音副檔名使用 `.m4a`。
- **即時額度預檢與防護**：生成前必須讀取配額表（`quota_planner`），配額不足直接標記 `QUOTA_WAIT` 並安全等待，禁止無效重試；碰到每日/每週上限就等額度窗重置，不用多帳號繞過。
- **不可信內容與路徑（ADR-013）**：講義、文獻、網路研究來源與 Gemini 回覆一律當資料：前端用 `escHtml()`，inline handler 參數用 `jsAttr()`，Markdown 經 `markdown_fragment()`（連結 scheme 白名單）；MCP 會新增、搬移、上傳或花額度的工具一律加 `confirm`。由使用者或 Agent 傳入的識別碼與路徑先過 `domain/path_safety.py`，只能落在 `DATA_DIR`、`STUDY_ROOT_DIR` 或課程登錄資料夾內。
- **網頁路徑一律用選的（2026-11-25 使用者定案）**：網頁上凡是需要檔案或資料夾路徑的地方，一律提供選擇方式（下拉選單、清單點選或資料夾／檔案挑選器），不要求使用者手打路徑；要新建的名稱（例如課本資料夾名）可以輸入，但要同時列出既有選項可直接選。新增或修改網頁功能時一併遵守，並在測試中檢查。
- **品質隔離門檻**：每份測驗必須達 30 題、全課程模擬考題數不足時，一律進入 `DATA_DIR/needs_review/` 隔離，工作狀態標為 `NEEDS_REVIEW`，並在總結報告中醒目標註。

## 3. 和通用規範不同的例外（要寫理由）

- （目前沒有）

## 4. 禁止事項

- 不修改、不搬移使用者課程資料夾中的 PDF（只讀）；唯一例外是使用者在網頁或 MCP（`confirm=True`）親自確認的整理動作：scratch 歸檔／撤銷歸檔（SPEC-016）、課本切割與把章節搬出 `02 Handouts`（SPEC-018）、`consolidate --apply`（ADR-015），且一律先預覽、不覆寫、不刪除。
- 程式不輸入、不保存 Google 密碼；登入由使用者在瀏覽器親自完成。圖書館（OpenAthens）帳密只能放 `.env` 的 `LIBRARY_EMAIL` / `LIBRARY_PASSWORD`（ADR-013）。
- 不自動刪除 Gemini Notebook 上的 notebook 或產出。

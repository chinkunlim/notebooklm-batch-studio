# 本專案專屬規則 (PROJECT_RULES)

> 規則分兩層：`docs/standards/` 的其他文件是**所有專案通用**的規範（由專案模板提供，`agentctl update` 會更新）；
> 本檔是**只適用這個專案**的規則，由這個專案自己維護，模板更新時不會被覆蓋。每次開工都要讀。

## 1. 領域知識與術語

- **課程**：一個 PDF 資料夾 = 一門課 = 一本 Gemini Notebook（Gemini Notebook），notebook 名稱 = 資料夾名稱。
- **講次**：課程中的一份 PDF，依檔名排序編號 `01, 02, …`。
- **產出**：audio (`.m4a`)、quiz（×3：1 基礎、2 理解、3 模擬考，各 30 題）、infographic、mind map、flashcards、study guide、concept explanation report；整門課另有模擬考與全課程 mind map。
- **產出組合（profile）**：`full`、`quiz-only`、`exam-prep`，見 SPEC-001。可於 Web 介面自由切換個別項目開關。
- **版本化重新生成**：重新生成時不覆蓋舊檔案，Gemini Notebook 遠端標題後綴 `(v2)`，本機檔名後綴 `_v2`（歷史紀錄於 `job_versions`）。
- **多裝置資訊圖表**：資訊圖表預設為直式，並由 `image_fitter` 同步輸出 A4 PDF、iPad Air 4 (2360x1640) 與 MacBook Pro 14 吋 (3024x1964) 規格。
- **學生研讀工作台 (Study Portal)**：整合線上互動測驗、作答記錄 (`quiz_attempts`)、錯題本 (`quiz_mistakes`)、3D 閃卡、語音播放與 Anki CSV 間隔重複匯出。
- **研讀計畫與間隔複習 (SPEC-007)**：每日「Today」學習任務排程、考前倒數天數動態調整、跨講混合複習、測驗題目之 Gemini Notebook AI 詳解快取 (`explanations`)。
- **學習心理學與智慧閱讀 (SPEC-008)**：講義 PDF.js 離線閱讀器、Gemini Notebook 核心重點萃取與引文畫線定位、艾賓浩斯半衰期記憶強度計算（連續天數與掌握度熱圖）、作答信心評分（sure-but-wrong 認知盲點強烈警示）、蘇格拉底式引導家教 (`tutor_messages`)、25 分鐘番茄鐘專注計時。
- **單一產出獨立設定 (SPEC-006)**：支援個別產出覆寫題目數（預設 30 題）、難度、語言、資訊圖表方向與風格、投影片格式（PDF/PPTX），採「全域預設 ➔ 課程設定 ➔ 講次覆寫」三層繼承。
- **研讀工作室與外觀自訂 (SPEC-009，規劃中、尚未實作，目前網頁是 design v2)**：奢華黑膠擬態唱盤、機械唱臂物理動態（播放落針/暫停抬起）、270° 環形進度弧線軌道、9 大產出物全景平鋪九宮格矩陣（免分頁切換）、頂部第 4 主分頁設計自訂、雙軌 RWD 選擇器與個人頭像自訂；所有迭代原型獨立歸檔於 `docs/design/`。

## 2. 本專案特有的規則

- **埠號**：正式 `HTTP_PORT=8768`；開發驗證 8769、隔離測試 8770。全機埠號以 `~/Desktop/projects/00 init_dev_env/PORTS.md` 為準，用新埠號前先查表並更新。啟動時若 8768 已被其他程式佔用，伺服器會在 log 中列出是哪個程式並停止。
- **命名與位置**：輸入 PDF 與 `course.toml` 放在 `DATA_DIR/input/courses/<課程代號>/`；下載產出檔 `<課程代號>_<講次>_<主題>_<類型>[-序號][_vN]`，例如 `BIO101_03_細胞膜_Quiz2-理解.md`，存放在 `DATA_DIR/output/courses/<課程代號>/<講次>_<主題>/`；不足 30 題之待審查項目放 `DATA_DIR/needs_review/`。Gemini Notebook 內只加 `[講次]` 前綴。
- **每份 PDF 單獨生成**：生成每講產出時只勾選該份 PDF（`source_ids=[source_id]`）；整門課產出才勾選全部。
- **保持來源 ID**：重新掃描註冊課程時，講義未變更者必須保留原有 `source_id`，禁止重複上傳至遠端筆記本。
- **操作 Gemini Notebook 只在 `adapters/`**：notebooklm-py 為主、Playwright 補位（ADR-001），語系代碼指定 `zh_Hant`，語音副檔名使用 `.m4a`。
- **即時額度預檢與防護**：生成前必須讀取配額表（`quota_planner`），配額不足直接標記 `QUOTA_WAIT` 並安全等待，禁止無效重試；碰到每日/每週上限就等額度窗重置，不用多帳號繞過。
- **品質隔離門檻**：每份測驗必須達 30 題、全課程模擬考題數不足時，一律進入 `DATA_DIR/needs_review/` 隔離，工作狀態標為 `NEEDS_REVIEW`，並在總結報告中醒目標註。

## 3. 和通用規範不同的例外（要寫理由）

- （目前沒有）

## 4. 禁止事項

- 不修改、不搬移使用者課程資料夾中的 PDF（只讀）。
- 程式不輸入、不保存 Google 密碼；登入由使用者在瀏覽器親自完成。
- 不自動刪除 Gemini Notebook 上的 notebook 或產出。

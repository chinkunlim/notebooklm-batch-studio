# SPEC-011：Gemini Notebook 探索提問、問答筆記庫與階層標籤系統

- **狀態**：Implemented <!-- Draft | Approved | Implemented | Deprecated -->
- **日期**：2026-11-14
- **相關任務 / ADR**：TASK-024 / ADR-010

---

## 1. 目標與背景 (Intent & Why)

### 1.1 背景
目前「Gemini Notebook 學習工作室」已具備批次生成 12 種學習產物、測驗解析（問 Gemini）與蘇格拉底家教功能。然而在學生自主研讀時，缺乏一個「**主動提問 ➔ 深入對話 ➔ 萃取結構化筆記 ➔ 反哺回筆記本來源**」的正向知識閉環：
1. 學生在研讀講義或測驗時，想對 NotebookLM 提出自由探索問題，但不想離開當前畫面。
2. 對話經過多輪討論後，得出有價值的核心觀念，希望將其沉澱為 Markdown 筆記（相容 Obsidian、Notion）。
3. 部分高價值筆記希望能一鍵回灌為 Gemini Notebook 的來源，讓後續的生成與家教都具備這些最新知識。
4. 測驗中答錯或感到疑惑追問的問題，本質是學生的「知識盲點」，應當集中整理至同一個筆記庫中，並透過標籤系統追蹤掌握度。

### 1.2 成功樣貌 (Success Criteria)
- 學生可隨時於研讀工作台右側滑出「提問抽屜」，亦可一鍵展開為「問答筆記庫」完整大頁面。
- 支援「全課程」或「指定單講／特定來源」提問，精準對焦。
- 提供「一鍵整理精華」按鈕，由 NotebookLM 依據固定規範直接產出帶有階層標籤的 Markdown。
- 支援本機 Markdown 儲存、複製、個人備忘追加，以及「單篇回灌」或「多篇合併打包回灌」至 Gemini Notebook。
- 測驗解析卡片具備「收錄至問答筆記庫」快捷操作，自動標記 `#類型/測驗追問` 與 `#掌握度/待加強`。
- 完整相容 Obsidian 巢狀標籤語法（`#大/中/小`）、Dataview 查詢與圖譜色彩視覺化。

---

## 2. 目標、非目標與反目標 (Goals, Non-goals & Anti-goals)

### 2.1 目標 (Goals)
1. **雙型態操作介面**：
   - 輕量抽屜（Drawer）：在講義閱讀器、測驗、錯題本中皆可隨時滑出，不中斷研讀動線。
   - 完整頁面（Full Tab）：研讀工作台新增「問答筆記」獨立分頁，提供歷史對話與筆記庫管理。
2. **NotebookLM 原生上下文總結**：在同一個 `conversation_id` 內直接請求格式化總結，無須依賴本機第三方 LLM。
3. **階層式標籤架構（由大到小）**：
   - `#課程/{課名}/{講次}`（如 `#課程/BIO101/L03`、相容簡短 `#L03`）
   - `#類型/{場景}`（如 `#類型/測驗追問`、`#類型/自主探討`）
   - `#掌握度/{狀態}`（如 `#掌握度/待加強`、`#掌握度/已搞懂`）
   - `#主題/{領域}/{核心概念}`（如 `#主題/生物學/卡爾文循環`）
4. **回灌防爆量保護**：守護 Gemini Notebook 50 份來源上限，支援講次問答「合併打包」為單一來源上傳。
5. **深度研讀聯動**：
   - 回答中的講義頁碼引用支援點擊跳轉至 PDF.js 對應頁。
   - 總結筆記附帶 1~2 題問答閃卡，一鍵匯入既有學習卡庫與 Anki。

### 2.2 非目標 (Non-goals)
- 不做即時多人協作聊天室（系統本質為單機單人隱私學習環境）。
- 不取代 Obsidian 本身：專注於生成出版級、排版規範相容的 Markdown 檔案，由使用者自由選擇在 Studio 內查閱或用 Obsidian 開啟。

### 2.3 反目標 (Anti-goals)
- **嚴禁暴力整串對話未經整理即上載為來源**：避免雜訊與口語問答污染 Gemini Notebook 的向量檢索品質。
- **嚴禁破壞使用者既有原始課程 PDF 資料夾**：所有產生的 Markdown 筆記嚴格存於 `DATA_DIR/output/courses/<course>/notes/`。

---

## 3. 方案評估與取捨 (Approaches)

### 方案 A（採納）：NotebookLM 原生對話與格式化閉環
- **做法**：
  1. 提問與多輪交談直接呼叫 `notebooklm-py` 的 `client.chat.ask(notebook_id, question, source_ids=..., conversation_id=...)`。
  2. 點擊「一鍵整理精華」時，在同一個 `conversation_id` 送入規格 Prompt，NotebookLM 依模板回傳標準 Markdown。
  3. 前端提供儲存、複製、追加備忘、切換掌握度，並透過現有 `source_manager` API 進行單篇或合併打包上傳。
- **優點**：架構乾淨、響應快、零外部模型依賴，且 NotebookLM 對該課來源的理解度最高。

### 方案 B（未採納）：雙模型後處理（NotebookLM 問答 + 本機 Ollama 二次排版）
- **缺點**：本機 Ollama 需佔用大量 GPU/RAM，引入額外延遲與環境依賴，且 NotebookLM 本身對 Markdown 格式遵守能力極佳，屬過度工程。

---

## 4. 功能詳細規格與動線 (Detailed Specifications)

### 4.1 雙入口介面設計
1. **隨身提問抽屜 (Sidebar Drawer)**：
   - 位於研讀工作台右側，浮動按鈕或快捷鍵（如 `⌘J`）可即時展開/收合。
   - 頂部包含：課程標籤、範圍切換器（[全部來源] 或 [第 X 講]）、[開啟新話題] 按鈕、[展開至大頁 ↗] 按鈕。
   - 中間為對話紀錄區，每則 NotebookLM 回答卡片下方提供「📌 存為單則筆記」。
   - 底部為「一鍵整理精華筆記」按鈕與輸入框。
2. **問答筆記庫大頁面 (Full Notes Studio Tab)**：
   - 研讀工作台分頁選單新增「問答筆記」（與講義、測驗、錯題、學習卡並列）。
   - 左側：標籤篩選雲（支援按課程、講次、類型、掌握度過濾）與筆記歷史清單。
   - 右側：筆記預覽與編輯區（Markdown 渲染、原始碼切換、個人備忘追加、掌握度狀態切換、加入/移除來源操作）。

### 4.2 NotebookLM 格式化 Prompt 規範
當使用者點擊「整理為精華筆記」時，系統在該對話中自動送出：
```text
請將我們剛才的所有討論內容，依照以下 Markdown 規格整理成一份完整的精華學習筆記：
1. 標題：以一級標題 (# ) 標註主題核心概念。
2. 標籤：輸出格式相容的標籤列，包含：
   - 課程歸屬：#課程/{course_code}/{lecture_slug} 及 #{lecture_slug}
   - 來源場景：#類型/{scene}
   - 掌握度：#掌握度/待加強
   - 主題概念：請根據內容提煉 2~3 個主題標籤（如 #主題/學科/核心概念）
3. 核心結論（TL;DR）：1~2 句話濃縮最重要觀念。
4. 深度重點解析：條列說明、公式或代碼塊、關鍵辨析。
5. 講義出處：引用的講義名稱與頁碼（若有）。
6. 隨堂記憶卡：以 Q: 與 A: 格式提供 1~2 題最容易混淆的複習題。
請直接以乾淨標準 Markdown 格式輸出，不要有多餘的問候語。
```

### 4.3 筆記儲存與檔案結構
- 儲存路徑：`$DATA_DIR/output/courses/<course_code>/notes/<note_id>_<slug>.md`
- 檔案開頭標準 YAML Frontmatter：
  ```markdown
  ---
  id: "note-20261114-1701"
  title: "光反應與卡爾文循環能量轉換機制"
  date: "2026-11-14T17:05:00+08:00"
  course: "BIO101"
  lecture_no: 3
  type: "quiz_followup"
  mastery: "needs_review"
  tags:
    - 課程/BIO101/L03
    - L03
    - 類型/測驗追問
    - 掌握度/待加強
    - 主題/生物學/卡爾文循環
  sources:
    - "Ch03-photosynthesis.pdf"
  ---
  ```

### 4.4 來源回灌機制
1. **單篇回灌**：呼叫 `upload_custom_source`，直接將單篇 `.md` 轉換/上傳至 Gemini Notebook。
2. **多篇合併打包回灌**：
   - 在筆記庫中可勾選多篇筆記（或點擊「打包本講筆記」）。
   - 系統將多篇 Markdown 組合為單一整合文件（`L03_隨堂問答精華總整理.pdf`），上傳至筆記本，僅佔用 1 份來源額度。

### 4.5 測驗與錯題庫打通
- 在測驗中（`studio.js`）與錯題本中（`studio-study-panels.js`），當點擊「為什麼？問 Gemini Notebook」顯示解析後，下方新增「📥 收錄為問答筆記」按鈕。
- 點擊後自動以題目、學生作答、正確答案與 AI 解析生成 Markdown 筆記，自動帶上 `#類型/測驗追問` 與 `#掌握度/待加強`。

---

## 5. 資料庫與 API 規格

### 5.1 資料庫表結構 (SQLAlchemy)
新增 `course_qa_notes` 資料表：
- `id` (VARCHAR PK)
- `course_code` (VARCHAR, FK courses.code)
- `lecture_no` (INTEGER, nullable)
- `title` (VARCHAR)
- `content_markdown` (TEXT)
- `personal_memo` (TEXT, nullable)
- `tags_json` (TEXT, JSON array of strings)
- `source_scene` (VARCHAR: `chat_drawer`, `study_tab`, `quiz_explain`)
- `mastery_status` (VARCHAR: `needs_review`, `mastered`)
- `is_uploaded_as_source` (BOOLEAN, default False)
- `uploaded_source_id` (VARCHAR, nullable)
- `created_at` (DATETIME)
- `updated_at` (DATETIME)

### 5.2 HTTP 路由與 MCP 工具

#### HTTP API
- `POST /api/courses/{code}/qa/ask`：發送提問至 NotebookLM。
  - Payload: `{ "question": str, "lecture_no": int | null, "conversation_id": str | null }`
  - Response: `{ "answer": str, "citations": list, "conversation_id": str }`
- `POST /api/courses/{code}/qa/summarize`：發送格式化總結指令至該對話。
  - Payload: `{ "conversation_id": str, "lecture_no": int | null }`
  - Response: `{ "markdown": str, "tags": list[str], "title": str }`
- `GET /api/courses/{code}/notes`：取得該課程所有問答筆記（支援 `?tag=`、`?lecture_no=`、`?mastery=` 篩選）。
- `POST /api/courses/{code}/notes`：建立或更新問答筆記（儲存 Markdown 檔案與 DB 記錄）。
- `PATCH /api/courses/{code}/notes/{note_id}/mastery`：切換掌握度狀態（`needs_review` ⇄ `mastered`）。
- `POST /api/courses/{code}/notes/{note_id}/push_to_source`：單篇筆記推播至 NotebookLM 來源。
- `POST /api/courses/{code}/notes/bundle_to_source`：多篇筆記合併打包推播至 NotebookLM 來源。
- `DELETE /api/courses/{code}/notes/{note_id}`：刪除筆記（可選是否同步刪除遠端 source）。

#### MCP 工具
- `ask_notebook_question(code, question, lecture_no=None)`
- `list_course_notes(code, tag=None)`
- `save_qa_note(code, title, content_markdown, lecture_no=None, tags=None)`
- `push_note_to_source(code, note_id, confirm=False)`

---

## 6. 驗收標準 (Acceptance Criteria)

- [ ] **提問抽屜與大頁**：在任一研讀畫面點擊即可滑出抽屜發問；點擊展開可切換至全螢幕問答筆記頁面。
- [ ] **範圍對焦**：可指定整門課或單一講次來源，NotebookLM 能依限定範圍回答並帶有正確引用。
- [ ] **精華總結格式**：點擊「整理為精華筆記」能獲得符合規範的結構化 Markdown，內含標題、結論、解析、引用與階層標籤。
- [ ] **階層標籤支援**：筆記生成的 Markdown 包含標準 Frontmatter 與 `#大/中/小` 巢狀標籤，在系統介面可點選篩選，Obsidian 能正確辨識為標籤樹。
- [ ] **測驗一鍵收錄**：測驗中追問的解析可直接存為筆記，自動賦予 `#類型/測驗追問`。
- [ ] **掌握度切換**：在介面上點擊切換掌握度，能同步更新資料庫與本機 `.md` 實體檔案中的標籤。
- [ ] **來源回灌與額度保護**：支援單篇回灌與多篇合併打包回灌至 Gemini Notebook，且不修改本機原始 PDF。
- [ ] **單元與整合測試**：新增之 Service、HTTP 路由與 MCP 工具具備離線 Mock/Dummy 完整測試，覆蓋率 100% 通過。

# SPEC-004：第二階段 — 學生研讀工作台、錯題本與間隔重複

- **狀態**：Implemented
- **日期**：2026-11-01
- **相關任務 / ADR**：`TASK-007`、[`ADR-003`](../adr/003-student-study-portal-spaced-repetition.md)

## 1. 目標

將批次生成後的產物（多風格測驗、抽認卡、心智圖、語音導讀、深度研習報告）無縫轉化為學生專屬的互動研讀工作台。學生可直接於瀏覽器進行線上作答，即時取得得分與選項解析；答錯之題目自動彙整至「弱點錯題集」，並支援一鍵匯出至 Anki 實現科學間隔重複 (Spaced Repetition)。

## 2. 使用情境

- **即時作答與自我評量**：學生切換講次，自由選擇「研究所深入版 (Academic)」或「考概念刷題版 (Concept Drill)」進行作答，交卷後即時高亮正確/錯誤選項並展開詳解。
- **錯題追蹤與弱點消除**：作答錯誤題目自動寫入後端 SQLite 資料庫；學生可於「📕 弱點錯題集」隨時複習錯題，完全理解後點擊「我已精通此題」進行消除。
- **間隔重複外掛整合**：點擊「📥 匯出錯題專屬 Anki 卡牌 (.csv)」或「匯出章節抽認卡」，一鍵匯入 Anki 軟體安排 SM-2 複習排程。
- **多媒體研習體驗**：
  - 🎙️ 內嵌 HTML5 音訊播放器，支援全課或單講語音導讀（0.75x~2.0x 倍速、快進快退、離線下載）。
  - 🗂️ 3D 翻轉卡牌，點擊概念正反面翻轉並支援隨機抽卡。
  - 📄 深度研讀報告預覽器（研習指南、簡報、心智圖、部落格文）。

## 3. 資料架構與模型

依循 Alembic 遷移版本 `4985a300eaa2`：

- **`quiz_attempts`**：
  - `id` (VARCHAR 36, PK)
  - `course_code` (VARCHAR 64, FK courses.code)
  - `lecture_no` (INTEGER, nullable)
  - `quiz_variant` (VARCHAR 64)
  - `score` (INTEGER)
  - `total_questions` (INTEGER)
  - `created_at` (DATETIME)
- **`quiz_mistakes`**：
  - `id` (VARCHAR 36, PK)
  - `attempt_id` (VARCHAR 36, FK quiz_attempts.id)
  - `course_code` (VARCHAR 64)
  - `lecture_no` (INTEGER, nullable)
  - `question_text` (TEXT)
  - `choices` (JSON)
  - `correct_index` (INTEGER)
  - `selected_index` (INTEGER)
  - `explanation` (TEXT)
  - `is_resolved` (BOOLEAN)
  - `created_at` (DATETIME)

## 4. API 規格與 MCP 工具 (核心規則 13)

### HTTP Endpoints
- `POST /api/courses/{code}/study/quiz-attempts`：提交作答與錯題資料。
- `GET /api/courses/{code}/study/history`：查詢測驗歷史分數與趨勢。
- `GET /api/courses/{code}/study/mistakes`：查詢弱點錯題（支援 `only_unresolved=true` 與講次篩選）。
- `POST /api/courses/{code}/study/mistakes/{id}/resolve`：消除特定錯題。
- `GET /api/courses/{code}/study/mistakes/anki.csv`：串流下載 Anki 錯題包 CSV。
- `GET /api/courses/{code}/study/flashcards`：取得講次抽認卡 JSON。

### MCP Tools
- `get_study_history(course_code, lecture_no)`：供 Agent 評估學生整體研讀進度。
- `get_weaknesses(course_code, lecture_no, only_unresolved)`：供 Agent 取得當前學生知識薄弱概念。
- `resolve_weakness_mistake(mistake_id, confirm=True)`：標記錯題已掌握（具備 safety confirm 協議）。

## 5. 驗收標準

- [x] 測驗分頁結構化載入，支援 Academic 與 Concept 雙版本。
- [x] 全課跨章複習 (`lecture_no == 0` / null) 正常載入 `_course_synthesis`。
- [x] 作答錯誤即時寫入資料庫並於弱點錯題集呈現。
- [x] 弱點消除即時反映至統計與卡片。
- [x] 匯出 Anki CSV 格式符合 RFC 4180 標準且可順利匯入 Anki。
- [x] 63 個單元與整合測試 100% 通過。

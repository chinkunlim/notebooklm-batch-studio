# 資料庫架構與遷移指南 (Database Schema & Migrations)

- **連線位置**：預設為資料目錄內的 `<DATA_DIR>/db/app.db`（`DATA_DIR` 在 `.env` 定義，位於專案目錄外）；如需連接其他資料庫，可在 `.env` 設定 `DATABASE_URL`。
- **資料表定義**：`src/notebooklm_batch_studio/adapters/db/models.py`。
- **資料存取層**：由 `adapters/db/` 下的各 Repository（`repository.py`, `study_repository.py`, `learning_repository.py`, `review_repository.py`）提供純 domain 物件讀寫，上層禁止直接存取 ORM 物件。
- **交易控管**：一律使用 `session_scope()`，成功時自動 commit，拋出例外時自動 rollback。

---

## 1. 資料庫實體綱要 (Schema & Tables)

系統共維護 12 張核心實體資料表：

| 資料表 | 用途 | 關鍵欄位 | 關聯 / 索引 |
|---|---|---|---|
| `courses` | 課程基本資訊、生成設定與筆記本映射 | `code` (PK), `name`, `source_dir`, `notebook_id`, `profile`, `language`, `mock_exam_questions`, `generation_options`, `selected_chapter_artifacts`, `selected_course_artifacts`, `paused`, `reuse_notebook` | `code` |
| `lectures` | 課程中的各講次 PDF 來源 | `id` (PK), `course_code`, `no`, `topic`, `filename`, `sha256`, `source_id`, `upload_status`, `error_message` | FK ➔ `courses.code`, 索引 `sha256`, `course_code` |
| `artifact_jobs` | 產出物非同步生成排程與工作佇列 | `id` (PK UUID), `course_code`, `lecture_no`, `artifact_type`, `status`, `attempts`, `version`, `artifact_ids`, `custom_prompt`, `style_options`, `interactive_path`, `quota_blocked_at`, `cooldown_until` | FK ➔ `courses.code`, 索引 `status`, `cooldown_until`, `artifact_type` |
| `quota_records` | Gemini Notebook 各類型配額消耗追蹤 | `artifact_type` (PK), `used_today`, `last_blocked_at`, `cooldown_until` | `artifact_type` |
| `quiz_attempts` | 學生測驗繳卷紀錄與信心統計 | `id` (PK UUID), `course_code`, `lecture_no`, `quiz_variant`, `score`, `total_questions`, `confidence_json` | FK ➔ `courses.code` |
| `quiz_mistakes` | 學生個人錯題本與掌握度紀錄 | `id` (PK UUID), `attempt_id`, `course_code`, `lecture_no`, `question_text`, `choices_json`, `correct_index`, `selected_index`, `explanation`, `is_resolved`, `confidence` | FK ➔ `quiz_attempts.id`, FK ➔ `courses.code` |
| `study_progress` | 學生研讀步驟完成紀錄（Today 計畫） | `id` (PK), `course_code`, `lecture_no`, `step`, `done_at` | 唯一約束 `(course_code, lecture_no, step)` |
| `review_items` | 閃卡與錯題之艾賓浩斯間隔複習排程 | `id` (PK), `course_code`, `lecture_no`, `kind`, `item_key`, `front`, `back`, `stage`, `due_at`, `last_reviewed_at` | 索引 `due_at`, `course_code` |
| `explanations` | Gemini Notebook 對測驗題目的 AI 詳解保存 | `id` (PK), `course_code`, `lecture_no`, `question_key`, `question`, `answer_md` | 索引 `course_code` |
| `key_points` | 講義 PDF 的 Gemini Notebook 重點標註萃取 | `id` (PK), `course_code`, `lecture_no`, `points_json` | 索引 `course_code` |
| `tutor_messages` | 蘇格拉底式引導家教對話歷程 | `id` (PK UUID), `course_code`, `lecture_no`, `role`, `text`, `conversation_id` | 索引 `course_code` |
| `ui_preferences` | 網頁偏好（設計與自訂、版面、欄寬、頭像、字型、每講音檔位置；ADR-009） | `key` (PK), `value`, `updated_at` | `key` |

---

## 2. 遷移管理流程 (Alembic Workflow)

當需要變更資料表結構時，遵循以下四步驟：

1. **修改模型**：編輯 `src/notebooklm_batch_studio/adapters/db/models.py`。
2. **自動產生遷移檔**：
   ```bash
   uv run alembic revision --autogenerate -m "說明變更內容"
   ```
   > 檢查產生的 `alembic/versions/` 檔案，補齊檔頭 docstring 說明。
3. **套用遷移至本機資料庫**：
   ```bash
   uv run alembic upgrade head
   ```
4. **驗證模型與遷移一致性**（`python3 scripts/agentctl.py check` 會自動執行）：
   ```bash
   uv run alembic check
   ```

---

## 3. 切換資料庫引擎

若需由 SQLite 改為 PostgreSQL：
```bash
uv add 'psycopg[binary]'
```
在 `.env` 中修改連線字串：
```env
DATABASE_URL=postgresql+psycopg://user:password@127.0.0.1:5432/notebooklm_studio
```

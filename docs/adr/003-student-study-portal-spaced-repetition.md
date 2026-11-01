# ADR-003：以 SQLite 與 Anki CSV 整合學生研讀工作台與間隔重複

- **狀態**：Accepted
- **日期**：2026-11-01
- **Agent**：`antigravity`
- **任務**：`TASK-007`

## 1. 背景與問題

NotebookLM 批次產出了高品質的測驗、抽認卡、心智圖、語音導讀與深度報告，但原本僅作為離線靜態檔案存在目錄中。學生在使用時缺乏完整的研讀與自我評量工作台，做錯的題目無法沉澱，無法追蹤學習弱點與落實間隔重複 (Spaced Repetition)。

需要設計一套兼具離線本機隱私、免複雜外部資料庫、且能銜接主流間隔重複工具（如 Anki）的架構。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. 純靜態 HTML (Local Storage) | 無需後端資料庫更動，所有測驗紀錄存於瀏覽器 LocalStorage | 無法跨裝置、換瀏覽器即遺失、無法提供 API 與 MCP 工具調用，不符合核心規則 13（網頁一定要能給 AI 工具用）。 |
| B. 本機 SQLite 關聯表儲存作答紀錄 + 動態生成 Anki CSV + FastAPI/MCP 三合一介面 | 1. 符合核心規則 13（HTTP、MCP、網頁共用一套 services）；2. 資料結構清晰（`quiz_attempts` 與 `quiz_mistakes`）；3. 支援弱點標記消除；4. 支援一鍵匯出 Anki 錯題包與章節抽認卡；5. 符合零外部依賴。 | 需要新增 Alembic 資料表遷移與後端 API 路由。 |

## 3. 決策與理由

選擇 **方案 B**：
1. **資料模型設計**：
   - `quiz_attempts`：記錄學生每一次作答的 course_code、lecture_no、variant、score、total_questions、created_at。
   - `quiz_mistakes`：外鍵關聯 attempt，記錄學生錯題的題幹、選項、學生選答、正確答案與解析，並具備 `is_resolved` 狀態。
2. **間隔重複整合 (Anki Export)**：
   - 提供符合 RFC 4180 標準的 CSV 格式，包含 Front、Back 與 Tags。
   - 錯題匯出包含題幹與詳解解析；抽認卡匯出支援概念翻轉卡牌。
3. **分層架構**：
   - `StudyRepositoryProtocol` -> `StudyRepository` (SQLAlchemy / SQLite)
   - `StudyTrackerService` (業務邏輯：記錄作答、查詢歷程、錯題消除、Anki CSV 串流)
   - 三大入口（HTTP Router `/api/courses/{code}/study`、MCP Server `get_study_history`/`get_weaknesses`/`resolve_weakness_mistake`、網頁 UI 研讀工作台）。

## 4. 影響與代價

- **正面影響**：打造封閉的學習反饋迴圈（研讀 -> 測驗評分 -> 弱點錯題集彙整 -> Anki 間隔重複複習 -> 弱點攻克消除），學生能清楚看見每章得分率與歷史進步軌跡。
- **代價**：SQLite 新增兩張資料表與外鍵約束，需透過 Alembic 保持版本遷移一致。
- **後續注意**：多執行緒存取時，FastAPI 透過 `scoped_session` 或每請求獨立 session 避免連線衝突。

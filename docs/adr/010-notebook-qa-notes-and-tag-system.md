# ADR-010：以 NotebookLM 原生上下文整理問答精華筆記與階層標籤回灌閉環

- **狀態**：Accepted <!-- Proposed | Accepted | Superseded by ADR-NNN -->
- **日期**：2026-11-14
- **Agent**：`antigravity`
- **任務**：`TASK-024`

## 1. 背景與問題

學生在研讀工作室閱讀講義或檢討測驗時，需要能就當下內容隨時向 Gemini Notebook 自由提問並進行多輪追問，進而將高價值的問答沉澱為結構化 Markdown 筆記（相容 Obsidian 階層標籤與雙向知識管理），並支援將精選筆記回灌為 NotebookLM 的自訂來源，形成「主動提問 ➔ 深入對話 ➔ 萃取結構化筆記 ➔ 反哺回筆記本來源」的學習閉環，同時須保護 NotebookLM 單本筆記本 50 份來源的上限且不破壞原始課程 PDF 資料夾。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A（採納）：NotebookLM 原生 `conversation_id` 上下文總結＋四維度階層標籤＋單篇/打包 PDF 回灌 | 零外部 LLM 依賴、響應快、直接利用同一對話完整上下文與來源引用；合併打包成單一 PDF 可守住 50 份來源上限 | 回灌後仍消耗少量遠端來源額度，需在介面追蹤上傳狀態與提供刪除選項 |
| B（未採納）：雙模型後處理（NotebookLM 問答＋本機 Ollama 二次排版） | 離線格式自由度高 | 需佔用大量本機 GPU/RAM，增加額外延遲與環境依賴；NotebookLM 原生遵守 Markdown Prompt 能力已足夠 |

## 3. 決策與理由

採納 **方案 A**：
1. 探索提問與多輪對話直接沿用 `notebooklm-py` 的 `conversation_id`，並在同對話內送出格式化總結 Prompt，產出含 YAML Frontmatter 與四維度 Obsidian 巢狀標籤（`#課程/{課名}/{講次}`、`#類型/{場景}`、`#掌握度/{狀態}`、`#主題/{領域}/{概念}`）的 Markdown 筆記。
2. 筆記同時持久化於 SQLite (`course_qa_notes` 資料表) 與 `DATA_DIR/output/courses/<course_code>/notes/`，確保使用者原始課程 PDF 資料夾完全不受變動。
3. 提供「單篇回灌」與「多篇合併打包轉為單一 PDF (`note_pdf_renderer.py`) 上傳」兩種來源回灌模式，並為具破壞性／寫入遠端的 MCP 工具（如 `push_note_to_source`）強制加上 `confirm` 保護參數，符合核心規則 13。

## 4. 影響與代價

- **正面影響**：不需額外啟動本機大模型即可提供「隨身抽屜 (`⌘J`) ＋ 問答筆記庫大頁 ＋ 測驗錯題一鍵收錄」完整閉環，且輸出格式相容 Obsidian 標籤樹。
- **代價與注意事項**：需定期留意筆記本遠端 50 份來源配額，多筆零散問答建議優先使用合併打包回灌；後續若修改標籤格式須保持與 `qa_notes_formatter.py` 及前端篩選雲一致。
- **相關文件與實作**：`SPEC-011` (`docs/specs/011-notebook-qa-notes-and-tag-system.md`)、`domain/qa_notes.py`、`adapters/db/notes_repository.py`、`services/qa_notes_service.py`、`services/qa_notes_formatter.py`、`services/converters/note_pdf_renderer.py`、`entrypoints/http/qa_notes.py`、`entrypoints/mcp_qa_notes.py`、`entrypoints/static/studio-qa-drawer.js`、`entrypoints/static/studio-notes-tab.js`、`tests/test_qa_notes_service.py`、`tests/test_qa_notes_api.py`、`tests/test_dummy_user_simulation.py`。

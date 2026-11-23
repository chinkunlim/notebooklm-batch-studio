# ADR-012：整合 note-studio 階段一：雙後端模組化 Markdown 筆記生成與縫合管線

- **狀態**：Accepted <!-- Proposed | Accepted | Superseded by ADR-NNN -->
- **日期**：2026-11-23
- **Agent**：`antigravity`
- **任務**：`TASK-026`

## 1. 背景與問題

`note-studio` 具備 7 模組結構化學習筆記生成與縫合能力，但其 PDF 向量排版引擎（Node/Chrome/ELK）仍有部分細節待收斂。為了先讓使用者在 `notebooklm-batch-studio` 中取得完整且保留後期排版語意標記（`[核心]`、`{{定義:...}}`、`:::QEC` 等）的單章 `.md` 原稿，決定分三階段整合：階段一先聚焦於「Prompt ➔ 生成 ➔ 驗證清洗 ➔ 模組縫合 ➔ 單章 `.md` 原稿」，暫不整合 PDF 排版渲染器。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. 僅透過外部 CLI 呼叫 `note-studio` | 短期改動小 | 無法共用統一學習目錄（ADR-011）、雙專案維護成本高、無法對齊三入口（HTTP/MCP/Web） |
| B. 分階段直接併入階段一純 `.md` 管線，支援雙後端（Gemini 網頁版為主、Gemini Notebook 為備用），Prompt 維持獨立 `.md` 檔案 | 立即獲得可手動修改的 Prompt 與乾淨 `.md` 原稿、完整保留語意 Tag 供階段三無痛銜接 PDF 排版、符合零容忍規範 | 需適配統一學習目錄路徑並為雙後端建立統一驅動介面 |

## 3. 決策與理由

採用 **方案 B**：
1. **獨立可編輯 Prompt（`assets/prompts/modular_specs/*.md`）**：直接沿用 `note-studio` 的獨立 Markdown 提示詞設計，程式僅讀取 `## Gemini 提示詞` 區塊並填入 `{{COURSE_NAME}}`、`{{CHAPTER_ID}}`、`{{CHAPTER_TITLE}}`；使用者手動測試時可直接修改 `.md` 檔，不需改動程式碼，並支援從 UI/API/MCP 預覽填入後的完整提示詞。
2. **雙後端支援**：預設測試與主力使用 **Gemini 網頁版（Playwright，`adapters/gemini/`）**，保留模型防降級偵測、額度恢復時間解析與 DOM 防漏讀取；同時提供 **Gemini Notebook（NotebookLM，`NotebookLMClient.ask_in_conversation`）** 作為備用方案，嚴格鎖定單一章節 `source_ids=[source_id]`。
3. **僅做模組縫合、暫不整合 PDF 渲染**：保留 `module_composer` 將 7 個模組檔縫合成單章 `.md` 原稿，略過 `compose_notes.py` 與 `adapters/renderer/`（Node/Chrome），待階段三再接回。

## 4. 影響與代價

- 新增 `assets/prompts/modular_specs/*.md`、`adapters/gemini/`、`services/notes/`、`entrypoints/http/notes.py`、`entrypoints/mcp_notes.py` 與對應 Web UI 面板與單元測試。
- 必須嚴格遵守本專案分層（`entrypoints ➔ adapters ➔ services ➔ domain ➔ config`）與零容忍 Code Review Guard（函式/檔案行數、參數數量 <= 4、完整 docstring 與 logger）。

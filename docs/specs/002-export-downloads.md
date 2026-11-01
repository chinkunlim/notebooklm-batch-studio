# SPEC-002：下載與轉檔（包含 NotebookLM 不給下載的產出）

- **狀態**：Implemented (Phase 1, TASK-001, TASK-003)
- **日期**：2026-10-21
- **相關任務 / ADR**：ADR-001

## 1. 目標

所有產出都要能存到本機。NotebookLM 網頁只讓 audio 與 infographic 下載，quiz、mind map、flashcards 不能下載，
所以程式要自己把內容取出並轉成好用的格式。這也是第二階段本機做題（SPEC-004）的資料來源。

## 2. 使用情境

- 使用者想把 quiz 印出來寫，或在沒有網路時複習。
- 使用者想把 flashcards 匯入 Anki、把 mind map 匯入 XMind。
- 第二階段的做題網頁讀取本機 quiz 資料。

## 3. 需求

### 必須 (Must)

**技術驗證（實作的第一個任務，先做再寫正式程式）**
用 1 本測試 notebook、1 份 PDF 實測下列各項，把結果寫進 ADR-001 的「驗證結果」：
1. notebooklm-py 能否在生成時只指定一份來源。
2. quiz、flashcards、mind map 能否用 notebooklm-py 取出**完整**內容（題目、選項、答案、解析、出處）。
3. 取不出來的項目，Playwright 讀網頁能否取出（逐題點開、展開全部節點）。
4. 每種產出的生成時間與 Pro 每日上限。
5. 產出能否改名（notebooklm-py 或 Playwright）。

**各產出的下載與轉檔**

| 產出 | 取得方式（依序嘗試） | 本機存成 |
|---|---|---|
| Audio | 直接下載 | `.m4a`（MP4/AAC） |
| Infographic | 直接下載 | `.png` |
| Study guide | 讀出文字 | `.md` |
| Quiz | notebooklm-py 取資料 → Playwright 讀網頁 | `.json`（原始資料）、`題目卷.md`、`答案卷.md`（含解析與出處）、可列印 `.pdf` |
| Flashcards | 同上 | `.json`、Anki 匯入用 `.csv`（正面、背面、標籤 = 課程代號＋講次） |
| Mind map | notebooklm-py 取樹狀資料 → Playwright 全展開截圖 | `.json`、`.md` 大綱、`.opml`（XMind 可匯入）、`.png` |

- 題目卷和答案卷分開，題目卷不顯示答案。
- 所有 `.json` 用統一格式（見 §4），不直接存 NotebookLM 的原始格式，NotebookLM 格式改變時只需改轉換層。
- 取出內容後驗證完整性：quiz 每題都有 4 個選項和 1 個正確答案；mind map 至少有根節點和一層子節點。不完整標為 `failed`。
- 下載檔一律依 SPEC-001 的命名規則存放。

### 可選 (Nice to have)
- Mind map 另存 Mermaid（`.mmd`），可放進 Markdown 筆記。
- Audio 另存逐字稿（若 NotebookLM 提供）。
- 一門課所有 quiz 合併成一本可列印的題庫 PDF。

### 不做 (Out of scope)
- 用 AI 自己重新出題（題目以 NotebookLM 產出為準）。
- 對 audio 做剪輯或轉檔成其他格式。

## 4. 介面 / API

統一的 quiz 格式：

```json
{
  "course": "BIO101",
  "lecture": "03",
  "variant": "2-理解",
  "source_pdf": "Lecture3 membrane.pdf",
  "prompt_version": "quiz-v1",
  "questions": [
    {
      "id": "BIO101-03-Q2-001",
      "question": "下列何者最能解釋 facilitated diffusion 不需要 ATP？",
      "choices": ["A ...", "B ...", "C ...", "D ..."],
      "answer": 2,
      "explanation": "...",
      "source": "p.12"
    }
  ]
}
```

統一的 mind map 格式：`{"title": "...", "children": [{"title": "...", "children": [...]}]}`。

flashcards：`{"cards": [{"front": "...", "back": "...", "source": "p.5"}]}`。

## 5. 驗收標準

- [ ] 技術驗證結果寫進 ADR-001，每一項都有「可行／不可行＋方法」。
- [ ] 一份 PDF 的 8 件產出都存在本機，檔名符合命名規則。
- [ ] quiz 的題目卷沒有答案；答案卷每題有答案、解析、出處。
- [ ] flashcards `.csv` 能匯入 Anki，mind map `.opml` 能匯入 XMind。
- [ ] 轉換層有離線測試（用存下來的範例資料，不連網）。

## 6. 未決問題

- quiz 的出處（頁碼）NotebookLM 是否提供；沒有的話答案卷只寫解析。
- mind map 截圖在節點很多時是否需要分段截圖或改用 SVG。

# SPEC-001：批次生成（資料夾 → Notebook → 每份 PDF 的複習包）

- **狀態**：Draft
- **日期**：2026-10-21
- **相關任務 / ADR**：ADR-001

## 1. 目標

使用者有多門課，每門課的 PDF 放在一個資料夾。程式自動完成：建立 notebook、上傳 PDF、
**每份 PDF 單獨勾選**生成一整套複習資料、改名、下載，最後回報結果。使用者不用手動一個一個操作。

成功的樣子：選 5 個資料夾 → 自動出現 5 本 notebook，每份 PDF 都有完整、命名一致的複習包，並收到完成通知。

## 2. 使用情境

- 學期初：把 5 門課的資料夾加入 → 程式排隊跑完（可能跨天，受每日上限影響）。
- 每週上新課：把新 PDF 丟進課程資料夾 → 資料夾監看自動只處理新的那份。
- 考前：對某門課套用「考前精華」組合，額外生成整門課的模擬考與精華 audio。
- 使用者在 NotebookLM 網頁上聽 audio、做 quiz、看 mind map 複習。

## 3. 需求

### 必須 (Must)

**資料夾與 notebook**
- 一個資料夾 = 一門課 = 一本 notebook，**notebook 名稱和資料夾名稱相同**。
- 一次可加入多個資料夾，每個資料夾各建一本 notebook。
- 若同名 notebook 已存在，沿用它，不重複建立。
- 每門課一個設定檔 `course.toml`（放在 DATA_DIR，不寫進 PDF 資料夾）：課名、課程代號、考試日期（選填）、產出組合、語言。

**講次**
- 依 PDF 檔名排序自動編號 `01, 02, …`；使用者可在 `course.toml` 覆寫講次與主題名稱。
- 主題名稱預設取檔名（去掉副檔名與開頭的數字）。

**每份 PDF 的產出（只勾選該份 PDF）**

| 項目 | 數量 | 設定 |
|---|---|---|
| Audio overview | 1 | Deep dive |
| Quiz | 3 | 各 30 題；Quiz1 基礎（記憶）、Quiz2 理解＋應用、Quiz3 考試模擬（綜合、易混淆） |
| Infographic | 1 | 統一 prompt |
| Mind map | 1 | |
| Flashcards | 1 | 名詞與定義 |
| Study guide | 1 | 重點摘要 |

10 份 PDF → 10 audio、30 quiz、10 infographic、10 mind map、10 flashcards、10 study guide。

**整門課的產出（勾選全部 PDF）**
- 模擬考 quiz 1 份（題數在 `course.toml` 設定，預設 50）。
- 全課程 mind map 1 張。
- 加入新 PDF 後，整門課產出標為「過期」，由使用者決定是否重做（不自動重做，以免消耗額度）。

**產出組合（取代一項一項勾選）**
- `full`（完整複習包）：上表全部。
- `quiz-only`：3 份 quiz + flashcards。
- `exam-prep`（考前精華）：整門課模擬考 + 全課程 mind map + 全課程 Brief 格式 audio。
- 組合定義在設定檔，可新增自訂組合。

**統一 prompt**
- Audio、quiz、infographic（以及其他支援自訂指示的項目）的 prompt 放在 `prompts/` 設定檔，有版本號。
- 預設語言：繁體中文，專有名詞保留英文。
- Quiz prompt 要求：每題 4 個選項且干擾選項合理、附解析與出處（頁碼或段落）、三份之間不重複題目。
- 生成紀錄寫下使用的 prompt 版本，之後改 prompt 可以知道哪些產出是舊版。

**Quiz 題數檢查**
- NotebookLM 的題數只有「較少／標準／較多」，不保證剛好 30 題。
- 生成後取出題目計算題數與重複題；不足 30 題時依序嘗試：重做（最多 2 次）→ 補做一份再合併。仍不足就標為「題數不足」並回報，不無限重試。

**命名**
- NotebookLM 內：只加講次前綴，例如 `[03] Quiz 2-理解`、`[03] Audio`（改名失敗不算整份失敗，記 log 即可）。
- 下載檔：`<課程代號>_<講次>_<主題>_<類型>[-序號]`，例如 `BIO101_03_細胞膜_Quiz2-理解.md`。
- 檔案放 `DATA_DIR/courses/<課程代號>/<講次>_<主題>/`。

**排隊、上限、續跑**
- 所有生成動作進入工作佇列（SQLite），每項狀態：`pending / running / done / failed / skipped / quota_wait`。
- 碰到每日上限 → 該類型改成 `quota_wait`，其他類型繼續做；隔天自動從斷點繼續。
- 各類型每日上限寫在設定檔（Pro 預設 audio 20/天，其他類型待技術驗證後填入）。
- 失敗會重試（指數退避，最多 3 次），仍失敗就標 `failed` 並記錄原因，可從網頁一鍵重試。
- 程式中斷或電腦關機後重開，從資料庫狀態繼續，不重複生成。

**跳過已完成、重複偵測**
- 用 PDF 內容雜湊（SHA-256）辨識；已完成的產出不重做。
- 內容相同但檔名不同的 PDF 只處理一次，並回報「重複」。

**資料夾監看**
- 可對每門課開關；偵測到新 PDF 後等檔案寫入完成（大小穩定）才排入佇列。

**回報**
- 每次執行結束：每門課一份結果表（成功、失敗與原因、題數不足、等待額度、重複）。
- 全部完成時 macOS 通知。
- 每門課自動產生**總覽頁**（Markdown + HTML）：每講所有產出的檔案連結與 notebook 連結。

**Log**
- 每次執行一個 run id；記錄每個外部呼叫、重試、跳過、額度等待與例外，不記 cookie 與帳號資訊。

### 可選 (Nice to have)
- Audio 可依課程設定改格式（Brief、Debate、Critique）與長度。
- 估算剩餘時間：依佇列數量與每日上限推算「預計 X 天完成」。

### 不做 (Out of scope)
- 本機做題、記分、錯題本（見 SPEC-004）。
- 一份 PDF 一本 notebook。
- 自動刪除 NotebookLM 上的 notebook 或產出。
- 多個 Google 帳號輪替來繞過上限。

## 4. 介面 / API

`course.toml` 範例（放在 `DATA_DIR/courses/BIO101/course.toml`）：

```toml
name = "BIO101 普通生物學"        # 也是 notebook 名稱的來源：預設 = 資料夾名稱
code = "BIO101"
source_dir = "/Users/me/課程/BIO101 普通生物學"
exam_date = "2026-12-20"
profile = "full"
language = "zh-TW"                # 繁中 + 英文術語
watch = true
mock_exam_questions = 50

[[lectures]]                      # 選填：覆寫自動編號
file = "Lecture3 membrane.pdf"
no = 3
topic = "細胞膜"
```

工作狀態（一筆生成工作）：

```json
{
  "course": "BIO101",
  "lecture": "03",
  "kind": "quiz",
  "variant": "2-理解",
  "status": "quota_wait",
  "attempts": 1,
  "prompt_version": "quiz-v1",
  "error": null,
  "files": []
}
```

錯誤情況：未登入或登入過期（全部暫停並通知使用者重新登入）、PDF 上傳失敗（檔案太大或損毀）、額度用完、
NotebookLM 介面或內部格式改變（標 `failed`，記錄錯誤）。

## 5. 驗收標準

- [ ] 加入 2 個資料夾 → 出現 2 本同名 notebook，PDF 都已上傳。
- [ ] 每份 PDF 都有 SPEC 表中的 8 件產出，生成時只勾選該份 PDF。
- [ ] 每份 quiz 有 30 題，三份之間沒有重複題；不足時會重做或補做，仍不足會被回報。
- [ ] 下載檔名全部符合命名規則。
- [ ] 中途結束程式再重開，不會重複生成已完成項目。
- [ ] 模擬達到每日上限時，該類型進入 `quota_wait`，其他類型繼續。
- [ ] 同內容不同檔名的 PDF 只處理一次。
- [ ] 資料夾放入新 PDF → 只處理新的那份。
- [ ] 完成時收到 macOS 通知，課程總覽頁連結都能打開。

## 6. 未決問題

- 實際 Pro 每日上限（quiz、infographic、mind map、flashcards）→ 技術驗證時記錄。
- 單本 notebook 的來源上限（Pro 約 300 份？）→ 待確認；超過時是否自動拆成第二本。
- 「只勾選一份來源」是否能透過 notebooklm-py 指定，或必須用 Playwright 操作勾選框 → SPEC-002 技術驗證。
- Infographic、mind map 是否支援自訂 prompt → 技術驗證。

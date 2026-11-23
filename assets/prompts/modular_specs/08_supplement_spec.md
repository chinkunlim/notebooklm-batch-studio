# 模組八：課外經典實驗補充與缺失填補規格（08_Supplement & Gap-Filling Specification）

> **認知學習目標**：深化背景理解與全書零缺失填補（Elaboration & Gap Filling）。課本中常出現「一句帶過」的重大經典實驗或歷史事件（如 Loftus 車禍記憶、Milgram 服從實驗、Belmont Report、Tuskegee 梅毒試驗），若無背景脈絡，學習者難以真正理解課本引用意圖；此外，當審查稽核（Audit）掃描出「未中文化之學習目標」或「缺少選項剖析之測驗題」時，本規範定義如何透過**結構化卡片原子注入**，在 100% 不破壞原稿排版的前提下自動精確補齊。

---

## 1. 核心設計原則與防竄改機制（ADR-008）

依據 **ADR-008**，為防範 LLM Agent 覆寫長篇 Markdown 筆記時發生「幻覺刪字、底線破壞、軟折行黏結」等排版災難：
1. **嚴格禁止 AI 直接修改 Markdown 原稿**：AI 不得覆寫 `courses/<科目>/原稿/ChXX.md` 或各模組檔案。
2. **結構化卡片中繼**：AI 僅需輸出標準 YAML 卡片（放置於 `DATA_DIR/courses/<科目>/supplements/inbox/*.yaml`）。
3. **程式原子注入與字元級零損驗證**：
   - 由 `scripts/supplement_manager.py --inject` 執行精確定位（唯一行錨點比對）。
   - 注入前後即時執行 `extract_core_tokens` 驗證，既有文字 100% 完整保留。

---

## 2. 三大結構化補充卡片格式（Card Schemas）

### 2.1 課外經典補充卡片（`type: supplement`）
當課本提及經典實驗或歷史事件時，建立兩層補充架構（正文插入簡短 `[補]` 摘要，並在章末追加詳細卡片）：

```yaml
type: "supplement"
chapter: "Ch04"
anchor_text: "Milgram 服從實驗造成極大爭議"  # 原稿中唯一的一行文字作為插入錨點
code: "S04-01"
summary_line: "- [補] Milgram（1963）權威服從實驗：65% 受試者施加最高電擊，引發知情同意與心理傷害省思 {補充=S04-01}"
source: "Milgram, S. (1963). Behavioral Study of obedience. JASP, 67(4), 371–378."
fields:
  背景: "探討二戰納粹戰犯辯解「服從命令」的心理機制。"
  做法: "受試者擔任「老師」，在權威實驗者命令下對答錯的假受試者施加遞增電擊（最高 450V）。"
  結果: "65% 受試者施加了致命級最高電擊，伴隨極度心理痛苦與壓力。"
  課本為什麼提: "突顯未充分知情同意、使用強烈欺瞞以及造成受試者極度心理壓力的倫理缺失。"
```

### 2.2 學習目標繁中化卡片（`type: objective`）
當稽核掃描出未翻譯或未繁中化的英文章節學習目標時使用：

```yaml
type: "objective"
chapter: "Ch02"
section: "2.1"
chinese: "區分量化研究中使用的各種變項類型（自變項、依變項、外在變項與中介/調節變項）"
english: "Differentiate among the types of variables used in quantitative research."
```

### 2.3 題目詳解與誘答剖析卡片（`type: quiz`）
當章末測驗題只有簡陋答案、缺少深度解析或缺少誘答選項剖析時使用：

```yaml
type: "quiz"
chapter: "Ch01"
question_identifier: "What is the main feature of an experiment?"
answer: "B"
explanation: "實驗研究法透過操弄自變項與控制混淆變項，是唯一能確立因果關係的方法。"
option_reasons:
  a: "相關法只能得知兩變項共同變化，無法確立因果。"
  c: "調查法主要用於描述母體特徵，無法操弄變項。"
  d: "個案研究缺乏控制，難以推論因果。"
```

---

## 3. 防偷懶與學術嚴謹性契約（Anti-Slacking Contract）
1. **出處真實性鐵律**：`source` 欄位必須是真實學術期刊論文、專著出版年份或官方調查報告，嚴禁虛構文獻。
2. **正文與章末雙層聯結**：正文 `summary_line` 必須包含 `{補充=SXX-YY}` 錨標籤，與章末卡片代號一對一呼應。
3. **誘答逐項解析**：選擇題選項誘答剖析不得偷懶合併，必須分別說明選項為何錯誤及其對應之真實概念。

---

## 4. Gemini 補充與缺失填補提示詞範本（Prompt Template for Gemini）

當執行 `uv run python scripts/supplement_manager.py --scan` 產出待補清單，或稽核發現缺漏時，提供以下提示詞給 Gemini：

````text
【角色設定】
你是一位出版級學術教科書主編與心理學方法論專家。你的任務是針對系統稽核掃描出的「待補充清單（Pending Supplements/Gaps）」，產出符合 note-studio 規格的結構化 YAML 卡片，嚴禁直接更動或輸出 Markdown 原稿。

【輸入資料】
科目：{{COURSE_NAME}}
章節：{{CHAPTER_ID}}
待補項目清單（由 supplement_manager.py --scan 產出）：
---
{{SCAN_TODO_LIST}}
---
章節原稿參考段落（用於選定唯一 anchor_text 錨點）：
---
{{CHAPTER_CONTEXT}}
---

【核心產出要求】
請嚴格輸出純 YAML 格式的卡片陣列（不含額外文字、開場白或 markdown 圍欄外的廢話），每個卡片依類型選擇：

1. 經典實驗或重要事件（type: supplement）：
   - 必須挑選原稿中客觀存在且全篇唯一的字串作為 anchor_text。
   - source 必須引用真實文獻（學者, 年代, 期刊名/專著名）。
   - fields 必須完整具備：背景、做法、結果、課本為什麼提 四大欄位，每欄 40~100 字。

2. 學習目標中文化（type: objective）：
   - chinese 欄位必須採用台灣教育部標準繁體中文心理學專業術語，語氣精練。

3. 題目詳解與誘答剖析（type: quiz）：
   - explanation 交代核心原理。
   - option_reasons 必須逐一列出所有錯誤選項為何錯誤（誘答分析）。
````

---

## 5. 自動化執行指令流水線

```bash
# 1. 掃描全書原稿，產出所有待補項目清單
uv run python scripts/supplement_manager.py --scan

# 2. Gemini 產出卡片存入 DATA_DIR/courses/<科目>/supplements/inbox/*.yaml
# 3. 執行原子級無損注入
uv run python scripts/supplement_manager.py --inject "DATA_DIR/courses/psychology/supplements/inbox/milgram_card.yaml"

# 4. 重新執行 Gate 3 嚴格稽核
uv run note-studio audit 1 --strict
```

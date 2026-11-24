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

- 新增 `assets/prompts/modular_specs/*.md`、`adapters/gemini/`、`services/notes/`、`entrypoints/http/{notes,gemini_auth}.py`、`entrypoints/mcp_{notes,gemini_auth}.py` 與對應 Web UI 面板與單元測試。
- 必須嚴格遵守本專案分層（`entrypoints ➔ adapters ➔ services ➔ domain ➔ config`）與零容忍 Code Review Guard（函式/檔案行數、參數數量 <= 4、完整 docstring 與 logger）。

## 5. 階段一刻意裁剪與不移植項目（決策與證據）

### 5.1 大綱字數契約（note-studio ADR-020 / `calculate_outline_words`）➔ 決議移除

- **證據**：`grep -rn calculate_outline_words src tests` 在刪除前僅命中 `src/notebooklm_batch_studio/domain/note_pipeline.py:173` 本身，全庫 **0 個呼叫端**；且 `note-studio` 之 `00_comprehension.md`（Step 0 配額契約來源）與 `services/golden_audit.py` 並未於階段一移植。
- **決議**：於 `TASK-033` 從 `domain/note_pipeline.py` 移除死碼 `calculate_outline_words`，不在階段一啟用動態字數契約門檻；待階段三引入 `00_comprehension.md` 與出版級 `golden_audit` 時再統一評估是否接回 `word_count.py`。

### 5.2 `StepValidator` 精簡對照（note-studio 342 行 + `density_checks.py` 265 行 ➔ 本專案 106 行）

| `note-studio` 原有檢查 | 來源位置 | 階段一處置與理由 |
|---|---|---|
| 空白輸出與制式拒答阻斷 | `step_validator.py` + `domain/model_audit` | **保留**（`services/notes/step_validator.py:85-93`，`is_gemini_refusal`），並整合至步驟驗證入口。 |
| `<!-- END -->` 截斷檢查與剝除 | `step_validator.py:48-60` | **保留**（`_strip_end_tag`，`step_validator.py:39-51`）。 |
| KaTeX 展示公式 `$$` 閉合檢查 | `step_validator.py:136-140` | **保留**（`_check_math_balance`，`step_validator.py:54-66`）。 |
| 行內數學 `$` 閉合檢查 | `step_validator.py:141-148` | **刻意刪除**：階段一尚未進入 KaTeX 瀏覽器排版，保留單個貨幣 `$` 符號可避免一般科目講義誤報失敗。 |
| `flowchart` 語法自動修復與檢查 | `step_validator.py:151-181`（依賴 `flowchart_syntax.py`） | **延至階段三**：階段一僅以 `STANDARD_NOTE_STEPS` 的 `required_tokens=("```flowchart",)` 檢查圍欄存在，自訂向量流程圖解析與畫布防溢歸 PDF 渲染階段。 |
| `mermaid` 括號成對檢查 | `step_validator.py:183-221` | **延至階段三**：階段一暫不做 Mermaid 渲染（ADR-012 §3），留待階段三排版檢驗。 |
| `BlockType` / QEC `Q:/E:/C:` 欄位正則與 `is_dom_fallback` 警告 | `step_validator.py:223-302` | **簡化保留**：改以 `NotePipelineStep.required_tokens` 統一檢查核心結構標記（如 `:::QEC`、`|`）；DOM 漏讀防護則直接由 `response_reader.py` 的基準數量比對（note-studio ISSUE-061）阻擋。 |
| 反偷懶佔位符檢查（`待補充`/`TODO`/`TBD`/`待補`） | `step_validator.py:101-120` | **延至階段三**：階段一允許先產出單章 `.md` 供人審核與單步重跑，避免初稿過度重試。 |
| `validate_module_density` 與 `density_checks.py`（跨模組錯位、60% 字數契約、學者引註 `>=5`、條列層級與角色標籤、`QEC >=3` / `Matrix >=2` / `Feynman >=3`） | `step_validator.py:304-342`, `density_checks.py:1-265`（note-studio ISSUE-054） | **不移植於階段一**：該規則高度耦合「心研法/Argon 7 步驟＋Step 0＋QEC」契約，不適用階段一通用課程提示詞；`response_reader.py` 已從傳輸層透過基線數量與「複製」按鈕限定容器防止抓取上輪舊回覆。 |

### 5.3 不移植之 `note-studio` 模組與測試清單（不做）

經比對 `/Users/limchinkun/Desktop/projects/note-studio/tests/test_*.py`（共 95 支測試檔）：
- **已移植（含 EQUIV 覆蓋）**：本專案 `tests/gemini/` 與 `tests/test_note_pipeline*.py` 已涵蓋 12 支測試檔（`tests/gemini/` 9 支，含 `TASK-031` 補齊之 `test_gemini_auth.py`；加上 `tests/test_note_pipeline_{behaviors,phase1,phase2}.py` 3 支，另見 `test_security_hardening.py`），覆蓋 Gemini Web session / CDP Chrome / selector / quota parser / baseline count / rename WARNING log / Gemini Auth / StepValidator / NotePipelineService。
- **刻意不移植之模組與測試（約 86 支原檔；部分邏輯由 `test_note_pipeline_behaviors.py` 轉寫對齊本專案介面，其餘留待階段三或已由本專案既有架構取代）**：
  - **PDF 排版渲染與格式樣本引擎（階段三範疇）**：`compose` / `compose_chapter` / `compose_layout` / `chrome_renderer` / `pdf_assembler` / `tree_engine` / `tree_wrap` / `flowchart*` / `grid` / `alignment` / `align_apply` / `page_layout_js` / `callout_parser` / `chapter_parser` / `density_validator` / `note_linter` / `spec_audit` / `specimen` / `text_auditor` / `source_editor` / `source_rules` / `diagrams_service_and_api`。
  - **獨立 Web 殼／學習與個人化（與本專案功能重複，採本專案既有模組）**：`api` / `mcp` / `db` / `greeting` / `learning_service` / `personalization` / `phase3_customization` / `archive_service` / `versions` / `supplement_injector` / `supplements_service` / `web_panels_elements` / `migrate` / `data_migrator`。
  - **獨立批次排程與字數契約細節（階段一以 `NotePipelineService` 簡化版取代）**：`chat_renamer`（功能併入 `chat_actions.py`）、`pipeline_coordinator` / `batch_orchestrator` / `batch_resilience` / `pipeline_chapter_status` / `pause_persistence` / `new_batch_clears_pause` / `step_validator` / `step_validator_cross_module` / `word_count_contract` / `dynamic_spec_builder` / `chapter_stitch_quarantine` / `gate3_needs_attention` / `rerun_archive` / `single_module_rerun` / `finalized_generation_guard` / `generation_*`（以上若階段三導入全書自動編排與 Gate 3 稽核，屆時再依需求移植）。

## 6. 附錄：程式碼引用之 `note-studio` 原始紀錄對照表

> 以下編號來自 `note-studio` 既有設計與除錯史；因階段一採取輕量併入（不複製獨立專案的歷史 ADR/ISSUE 流水號，避免與本專案 ADR-001~013 / ISSUE-001~056 衝突），統一於此附錄列出原始檔案路徑與處置方式（所有程式註解均已依 ISSUE-052 標明 `note-studio` 前綴）。

| `note-studio` 編號 | 原專案文件路徑 (`/Users/limchinkun/Desktop/projects/note-studio/docs/...`) | 本專案處置 | 程式碼引用位置 |
|---|---|---|---|
| **ADR-015** | `docs/adr/015-module-prompts-single-source-in-md.md` | 本 ADR §3.1 已完整吸納「獨立 `.md` 提示詞為唯一來源」設計，列於附錄對照 | `services/notes/module_prompts.py`（見 `SPEC-017`） |
| **ADR-016** | `docs/adr/016-batch-auto-retry-selective-scheduling-and-preference-persistence.md` | 僅沿用分頁/章節後關閉分頁機制，批次排程未移植；列於附錄對照 | `adapters/gemini/web_driver.py:87` |
| **ADR-017** | `docs/adr/017-flowchart-spec-alignment-and-canvas-containment.md` | 僅保留提示詞中的 ```flowchart 區塊語法要求，渲染器屬階段三；列於附錄對照 | `assets/prompts/modular_specs/01_mindmap_spec.md:16` |
| **ADR-019** | `docs/adr/019-module-stitch-failure-isolation.md` | `needs_review` 隔離細則未移植（本專案失敗標記 `status=failed` 且不覆寫已縫合稿）；列於附錄對照 | `services/notes/note_pipeline_service.py`、`ADR-012 §5.3` |
| **ADR-020** | `docs/adr/020-outline-word-count-contract.md` | 階段一刻意不移植（無 `00_comprehension` / `golden_audit`），已刪除死碼並於 §5.1 說明理由 | `ADR-012 §5.1` |
| **ADR-021** | `docs/adr/021-rerun-archive-and-regeneration.md` | 已於 `NotePipelineService` 實作重跑前版本歸檔（`versions/<chapter>/<stamp>`）；列於附錄對照 | `services/notes/note_pipeline_service.py:62, 252, 280`、`SPEC-013` |
| **ISSUE-034** | `docs/known-issues/034-gemini-rename-still-fails.md` | 改名失敗記錄 `WARNING` log 之修復已直接併入；列於附錄對照 | `adapters/gemini/chat_actions.py`、`tests/gemini/test_gemini_rename_logs.py` |
| **ISSUE-039** | `docs/known-issues/039-google-rejects-sign-in-in-playwright-browser.md` | 真實 Chrome CDP + 本專案 `ISSUE-053`（`TASK-031`）補齊登入入口；摘要並追蹤於本專案 `ISSUE-053` | `adapters/gemini/{chrome_session,browser_session,auth_runtime}.py`、`tests/gemini/test_{chrome_session,gemini_auth}.py` |
| **ISSUE-043** | `docs/known-issues/043-gemini-quota-limit-reached-selector.md` | 英文 `Limit reached` selector 與 strict mode 防護已併入；列於附錄對照 | `adapters/gemini/{selectors,web_driver}.py`、`tests/gemini/test_gemini_adapter.py` |
| **ISSUE-050** | `docs/known-issues/050-batch-generation-hang-and-launch-lock-deadlock.md` | Playwright watchdog、`_acquire_launch_lock` 超時、stale port 清理已併入；列於附錄對照 | `adapters/gemini/{browser_session,chrome_session}.py`、`tests/gemini/test_{browser_session,chrome_session,playwright_startup_timeout}.py` |
| **ISSUE-054** | `docs/known-issues/054-partial-step-failure-marked-done-and-module-crosstalk.md` | 回覆等待/失敗不標 done 已併入（跨模組密度檢查裁減理由見 §5.2）；列於附錄對照 | `tests/gemini/test_gemini_adapter.py:97`、`ADR-012 §5.2` |
| **ISSUE-058** | `docs/known-issues/058-copy-button-selector-sidebar-match.md` | 限縮最後一則回覆容器與 `copy_response_from_button` 解析已併入；列於附錄對照 | `adapters/gemini/{selectors,web_driver,response_reader}.py`、`tests/gemini/test_gemini_copy_selector.py` |
| **ISSUE-061** | `docs/known-issues/061-dom-fallback-reads-previous-turn-response.md` | baseline 回覆計數防錯讀舊回覆已併入；列於附錄對照 | `adapters/gemini/{web_driver,response_reader}.py`、`tests/gemini/test_{gemini_adapter,gemini_response_count_baseline}.py` |
| **ISSUE-065** | `docs/known-issues/065-premature-quota-auto-resume-before-reset-window.md` | Quota 恢復時間解析與 1 小時保底已併入；列於附錄對照 | `adapters/gemini/web_driver.py`、`domain/quota_parser.py`、`tests/gemini/test_quota_resume_parser.py` |
| **SPEC-017** | `docs/specs/017-note-learning-spec-and-modular-prompts.md` | 階段一提示詞契約對應本專案 `SPEC-013`；列於附錄對照 | `assets/prompts/modular_specs/MODULAR_SPECS.md:4` |
| **SPEC-019** | `docs/specs/019-custom-header-footer-naming-and-auto-quota-resume.md` | 本專案僅承接 Quota 自動解析恢復部份，對應本專案 `SPEC-013`；列於附錄對照 | `tests/gemini/test_quota_resume_parser.py:1`、`adapters/gemini/web_driver.py:303` |

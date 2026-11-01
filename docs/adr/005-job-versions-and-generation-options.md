# ADR-005：工作記錄自己的 artifact id 與版本號，重新生成保留舊版；產出參數以字串存於課程

- **狀態**：Accepted <!-- Proposed | Accepted | Superseded by ADR-NNN -->
- **日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-009`

## 1. 背景與問題

使用者要能對已生成的產出「重新生成」，而且要看得出哪一份是新的；也要能為每門課設定 NotebookLM 的生成參數
（資訊圖表方向、語音形式、投影片格式…）。原本：

- 一個「課程 × 講次 × 類型」只能有一個工作（`enqueue_jobs` 依這三者去重），重新生成只能覆蓋。
- 工作不記錄它在 NotebookLM 產生了哪些 artifact / note，事後無法補改名（心智圖就因此一直沒改名，ISSUE-011）。
- `ArtifactJob.style_options` 欄位存在但沒有任何地方使用。

## 2. 評估過的方案

| 方案 | 優點 | 缺點 |
|---|---|---|
| A. `artifact_jobs` 加 `version` 與 `artifact_ids`；去重鍵加上 version；`courses` 加 `generation_options`（JSON） | 舊版完整保留；可追溯每份產出；設定跟著課程走 | 需要一次 migration |
| B. 重新生成時重設舊工作為 PENDING | 不用改 schema | 舊檔被覆蓋、NotebookLM 上兩份同名，無法分辨 |
| C. 產出參數放在每個工作的 `style_options` | 可逐份設定 | 使用者要的是「這門課的資訊圖表都用直式」，逐份設定太瑣碎 |

## 3. 決策與理由

選 A。

- 重新生成建立 `version = 目前最大版本 + 1` 的新工作；NotebookLM 標題加「 (v2)」，本機檔名加「_v2」，舊版不刪除
  （也符合專案規則「不自動刪除 NotebookLM 上的產出」）。
- 每個工作完成後把產生的 id 寫進 `artifact_ids`，之後改名、同步、版本比對都靠它。
- `GenerationOptions` 是 domain 的 frozen dataclass，值一律存成 notebooklm-py enum 成員名稱的小寫字串
  （例如 `portrait`），只有 adapter（`generation.generation_kwargs`）會轉成 enum，service 與 domain 不依賴 notebooklm-py（ADR-001）。
- 課程重新註冊（再跑 batch / watcher）時不覆蓋已存的 `generation_options`。

## 4. 影響與代價

- Migration `d6e896ae4e2c`：`artifact_jobs.version`（預設 1）、`artifact_jobs.artifact_ids`、`courses.generation_options`。
- `NotebookLMClientProtocol`：`generate_quiz / flashcards / audio / slide_deck / infographic / video` 多一個 `options`；
  新增 `rename_mind_map`；`download_slide_deck` 多 `output_format`。
- 新入口：HTTP `GET/PUT /api/courses/{code}/options`、`POST /api/courses/{code}/jobs/regenerate`、`GET /api/naming-guide`；
  MCP `get_course_options`、`set_course_options`（confirm）、`regenerate_artifact`（confirm）、`get_naming_guide`。
- 資訊圖表裝置版本（A4 PDF、iPad Air 4、MacBook Pro 14）在本機用 Pillow 補白邊產生，不裁切、不多花額度。

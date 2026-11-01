# 已知問題 (Known Issues)

記錄「踩過的坑」：值得記住的 bug、外部服務的怪行為、環境問題，以及它們的根本原因與修正方式。
除錯時先查這裡：`grep -rn "關鍵字" docs/known-issues .agents/conversations`（後者只在本機）。

- 新增：`python3 .agents/skills/adr-issue-tracker/scripts/tracker_cli.py --add-issue <slug> --title "標題" --summary "錯誤訊息" --agent <名字>`
- 格式：[`_TEMPLATE.md`](_TEMPLATE.md)；在修正的程式碼註解加 `Refs: ISSUE-NNN`，並寫防回歸測試。
- 狀態：🔴 未解決 (open) → 🟡 已規避 (mitigated) → 🟢 已根治 (resolved)

> 命名規則：`_TEMPLATE.md` 是新增紀錄時要照著寫的範本；紀錄檔命名為 `NNN-<slug>.md`。整個專案只有根目錄一份 `README.md`。

## 總表

| ISSUE | 狀態 | 標題 | 現象 | 程式與測試 |
|---|---|---|---|---|
| [ISSUE-001](001-ollama-refine-noop.md) | 🟢 已根治 (Resolved) | Ollama 提示詞改寫實際上沒有呼叫 Ollama | refine_course_prompts_with_ollama 回報成功改寫 N 筆，但 prompt 內容其實沒變 | `services/orchestrator.py`, `entrypoints/api.py`, `entrypoints/mcp_server.py` |
| [ISSUE-002](002-quiz-needs-review-status.md) | 🟢 已根治 (Resolved) | 題數不足的測驗被標成 DONE 而非 NEEDS_REVIEW | 湊不滿 30 題的測驗已隔離到 needs_review/，但工作狀態是 DONE，總覽報告看不到需審查警告 | `services/artifact_runner.py`, `services/worker_pool.py`, `adapters/db/repository.py` |
| [ISSUE-003](003-nlm-output-language-english.md) | 🟢 已根治 (Resolved) | NotebookLM 產出語言預設為英文 | 語音、投影片、資訊圖表等未傳 language，函式庫預設 en；報告傳了無效代碼 zh-TW | `adapters/notebooklm/generation.py`, `adapters/notebooklm/client.py` |
| [ISSUE-004](004-artifact-wrong-lecture.md) | 🟢 已根治 (Resolved) | 下載與改名可能對到別的講次或未完成的產出 | 下載未帶 artifact_id、多數類型未等完成就下載、改名取最新一份、download_audio 下載兩次 | `adapters/notebooklm/client.py`, `services/artifact_runner.py` |
| [ISSUE-005](005-quota-status-ignored.md) | 🟢 已根治 (Resolved) | 配額拒絕以 failed 狀態回傳時未被偵測 | generate 回傳 USER_DISPLAYABLE_ERROR 的 failed 狀態而非例外，程式未檢查，未進 QUOTA_WAIT；冷卻固定猜 1 小時 | `adapters/notebooklm/quota.py`, `adapters/notebooklm/generation.py`, `services/orchestrator.py` |
| [ISSUE-006](006-reregister-drops-source-ids.md) | 🟢 已根治 (Resolved) | 重新註冊課程會清掉 source_id，導致重複上傳 | save_course 刪除並重建講次紀錄時沒保留 source_id，再跑 batch 或 watcher 觸發時會把所有 PDF 重新上傳到同一本筆記本 | `adapters/db/repository.py` |
| [ISSUE-007](007-audio-m4a-named-mp3.md) | 🟢 已根治 (Resolved) | 語音檔實際是 MP4/AAC，卻存成 .mp3 | 副檔名寫死 .mp3、網頁宣告 audio/mpeg，部分播放器打不開；同步服務也把資訊圖表猜成 .pdf | `services/artifact_runner.py`, `services/sync_service.py`, `entrypoints/http/artifacts.py`, `entrypoints/static/index.html` |
| [ISSUE-008](008-quota-blind-scheduling.md) | 🟢 已根治 (Resolved) | 排程不看即時額度，預估天數用猜的 | 額度不足仍送出請求；預覽固定用每天 100 個估算且任務數算錯；每次額度等待都吃掉重試次數 | `services/quota_planner.py`, `services/orchestrator.py`, `adapters/db/repository.py` |
| [ISSUE-009](009-mock-exam-not-quarantined.md) | 🟢 已根治 (Resolved) | 整門課模擬考題數不足仍標成完成 | `_process_mock_exam` 忽略「是否完整」旗標，不完整的考卷照樣存進正式產出並標 DONE | `services/artifact_runner.py` |
| [ISSUE-010](010-needs-review-not-downloadable.md) | 🟢 已根治 (Resolved) | needs_review 的檔案在網頁上無法下載 | 隔離檔不在課程產出資料夾內，下載路由找不到；路徑穿越檢查用字串前綴比對 | `services/orchestrator.py`, `entrypoints/http/artifacts.py` |
| [ISSUE-011](011-mind-map-not-renamed.md) | 🟢 已根治 (Resolved) | 心智圖在 NotebookLM 上沒有改名 | 心智圖是 note，artifacts.rename 改不到，程式直接跳過；改用 mind_maps.rename | `adapters/notebooklm/client.py`, `services/artifact_runner.py` |
| [ISSUE-012](012-wrong-extensions-and-download-link.md) | 🟢 已根治 (Resolved) | 投影片與資料表副檔名錯誤，網頁下載連結忽略 rel_path | 投影片 PDF 存成 .md、資料表 CSV 存成 .md；網頁只用檔名組下載網址 | `services/artifact_runner.py`, `entrypoints/static/index.html` |
| [ISSUE-013](013-report-html-raw-text.md) | 🟢 已根治 (Resolved) | 報告的 HTML 頁面只是原始文字 | Markdown 原文直接放進 pre，沒有轉換也沒有跳脫 | `services/converters/report_converter.py`, `services/artifact_runner.py` |
| [ISSUE-014](014-artifact-selection-not-saved.md) | 🟢 已根治 (Resolved) | 網頁勾選的產出內容沒有存進資料庫 | 勾選只存在 domain 物件，重新註冊後退回 profile 預設 | `adapters/db/models.py`, `adapters/db/repository.py` |
| [ISSUE-015](015-cli-tests-use-real-db.md) | 🟢 已根治 (Resolved) | CLI 測試讀寫真實資料庫 | 測試呼叫 main() 時 load_config 指向 DATA_DIR 的資料庫 | `tests/test_services_and_cli.py` |
| [ISSUE-016](016-report-instructions-ignored.md) | 🟢 已根治 (Resolved) | 報告的自訂指示被忽略；概念解說格式在網頁連線被拒絕 | 預設格式只讀 extra_instructions；網頁連線政策關閉 CONCEPT_EXPLANATION，改用 CUSTOM | `adapters/notebooklm/client.py` |
| [ISSUE-017](017-quiz-prompts-ten-questions.md) | 🟢 已根治 (Resolved) | 測驗 prompt 只要求 10 題，且寫死研究法領域 | 每份測驗需多批才湊滿 30 題、NotebookLM 同名重複；prompt 不適用其他科目 | `services/prompt_generator.py`, `services/artifact_runner.py` |
| [ISSUE-018](018-study-portal-quiz-missing.md) | 🟢 已根治 (Resolved) | 學習專區的測驗分頁打不開測驗 1/2/3 | 分頁寫死兩種進階測驗，沒跟上預設改用的測驗 1/2/3 與版本檔名 | `entrypoints/static/index.html` |
| [ISSUE-019](019-start-checkbox-ignored.md) | 🟢 已根治 (Resolved) | 「加入後立即開始」取消勾選無效 | 佇列已自動運作，新工作一進佇列就被認領；改為課程層級暫停 | `adapters/db/repository.py`, `entrypoints/static/index.html` |
| [ISSUE-020](020-web-field-mismatch.md) | 🟢 已根治 (Resolved) | 網頁課程卡片與學習專區閃卡讀錯欄位／路徑 | 卡片讀不存在的欄位；閃卡以檔名找講次但講次在資料夾名稱 | `entrypoints/static/index.html`, `services/study_service.py` |
| [ISSUE-021](021-answer-position-bias.md) | 🟢 已根治 (Resolved) | 測驗正確答案大多是 A | NotebookLM 傾向把正解放第一個；解析時改為固定種子打亂 | `services/converters/quiz_converter.py` |
| [ISSUE-022](022-quiz-submit-resets-view.md) | 🟢 已根治 (Resolved) | 交卷後測驗被重置並跳回第 1 講 | 交卷後更新統計的函式會選回第一講並重繪分頁 | `entrypoints/static/index.html` |
| [ISSUE-023](023-db-connection-leak.md) | 🟢 已根治 (Resolved) | 網頁用久了出現 Failed to fetch（資料庫連線耗盡） | scoped_session 以執行緒為範圍，執行緒池每條執行緒都佔住一條連線 | `entrypoints/api.py` |
| [ISSUE-024](024-buttons-calling-missing-routes.md) | 🟢 已根治 (Resolved) | 部分按鈕呼叫不存在的 API（Prompt 編輯、立即喚醒、裝置版資訊圖表） | 前端按鈕呼叫的路由從未實作；下載路由只接受 GET | `entrypoints/http/queue.py`、`http/artifacts.py`、`static/studio-core.js` |
| [ISSUE-025](025-linux-time-wait-so-reuseaddr.md) | 🟢 已根治 (Resolved) | Linux TCP 要求 TIME_WAIT 前後 socket 皆啟用 SO_REUSEADDR 否則 bind 失敗 | CI (Ubuntu 24.04) 執行 test_recently_closed_port_is_free 失敗，而 macOS 通過。原因為 Linux kernel 規定若原 socket 未設 SO_REUSEADDR，後續 socket 即使開啟 SO_REUSEADDR 亦無法重用 TIME_WAIT port。 | TODO |

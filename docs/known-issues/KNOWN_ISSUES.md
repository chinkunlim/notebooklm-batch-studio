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

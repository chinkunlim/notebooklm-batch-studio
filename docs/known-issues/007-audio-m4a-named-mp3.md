# ISSUE-007：語音檔實際是 MP4/AAC，卻存成 .mp3

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-01
- **Agent**：`claude-code`
- **任務**：`TASK-008`

## 1. 現象

完整跑完一門課後，6 個語音檔副檔名是 `.mp3`，但 `file` 顯示為 ISO Media（MPEG-4 / DASH），macOS `afinfo` 打不開，部分播放器無法播放。

- **錯誤訊息**：`Fail: AudioFileOpenURL failed`（afinfo）
- **重現步驟**：跑任一含 AUDIO 的 profile，對下載的 `*_audio.mp3` 執行 `file` / `afinfo`
- **影響範圍**：語音下載（`ArtifactRunner._process_audio`）、遠端同步（`sync_service.get_extension_for_kind`）、網頁學習頁的 `<audio>` 播放器

## 2. 根本原因

NotebookLM 提供的語音是 MP4 容器裝 AAC 音訊，程式卻寫死 `.mp3` 副檔名；網頁 `<source type="audio/mpeg">` 也宣告錯誤格式。
同步服務另外把資訊圖表猜成 `.pdf`，實際下載的是 PNG。另外 Python `mimetypes` 對 `.m4a` 回傳 `audio/mp4a-latm`，瀏覽器不一定接受。

## 3. 修正或規避方式

- 語音改存 `.m4a`；同步服務語音用 `.m4a`、資訊圖表用 `.png`。
- 下載路由對 `.m4a` 明確回傳 `Content-Type: audio/mp4`；網頁 `<source>` 不再寫死 type。
- 既有的 115-1 課程 6 個語音檔已改名為 `.m4a`，DB `artifact_jobs.output_file` 同步更新。

## 4. 防回歸

- `tests/test_notebooklm_generation.py`：`test_audio_is_saved_as_m4a`
- `tests/test_api_and_mcp.py`：`test_m4a_audio_download_is_served_as_audio_mp4`
- `tests/test_domain_and_queue.py`：`test_remote_sync_helpers_and_service`（副檔名斷言）

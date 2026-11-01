# SPEC-008：學習輔助（課件閱讀與重點標示、遺忘曲線、信心評分、交錯練習、家教）

- **狀態**：Implemented
- **日期**：2026-11-01
- **相關任務 / ADR**：TASK-009 / ADR-006

## 1. 目標

讓學習頁不只放產出，而是用學習心理學引導學生「先回想、分散複習、找出誤解」，並能直接回到課件看重點。

## 2. 使用情境

學生打開「🏠 今天」：
- 看到上次停在哪裡、哪一講快忘了、連續學習了幾天。
- 讀課件時，重點已經標好顏色。
- 做測驗時先評估自己有多確定。
- 卡住時問家教，家教用提問引導。

## 3. 需求

- **必須**：
  - **課件**：只讀方式提供已註冊的講義 PDF；檔案路徑不能超出課程資料夾。用 pdf.js 顯示，頁面捲到時才繪製。
  - **重點**：只問一次 Gemini Notebook 並存進 `key_points`，之後重複使用；`force` 可以重新問。重點用逐字引句比對 PDF 文字層：
    - 頁碼容許差一頁。
    - 行尾連字號拆開的字（`mar-` + `riage`）會先接回再比對。
    - 找不到的重點在清單上顯示為淡色。
  - **記憶強度**：依指數衰減 R = exp(−t/S) 估計（`domain/memory_model.py`）。
    - 測驗：分數 ≥80% 時 S×2.5、≥60% 時 S×1.3，否則 S 減半。
    - 閃卡：S = 該階段的複習間隔 × 2.8，也就是到期那天約剩 70%。
    - 分三級顯示：穩固 ≥70、開始遺忘 ≥40、快忘了 <40。
  - **連續學習天數與 28 天熱力圖**：學習活動包括交卷、複習閃卡或錯題、標記完成、問家教。
  - **上次停在**：存在瀏覽器（localStorage），記錄講次、分頁、測驗與答到第幾題。
  - **信心評分**：每題可選「很確定／不太確定／用猜的」。
    - 錯題記錄 `quiz_mistakes.confidence`。
    - 每次作答記錄 `quiz_attempts.confidence_json`（`sure_wrong`、`guess_right`、`rated`）。
    - 交卷後列出「很確定卻答錯」與「猜對」的題目。
  - **峰終回饋**：交卷後與同一份測驗的上一次成績比較。
  - **交錯練習**：「🔀 混合複習」從各講測驗隨機抽 20 題，記錄為 `mixed_review`（全課程）。
  - **生成效應**：可以「先回想再看選項」（選項模糊化）；閃卡上方有作答框。
  - **專注計時**：25 分鐘番茄鐘，結束時提示休息並回想重點。
  - **家教**：蘇格拉底式的 prompt，用 `conversation_id` 延續同一段對話，雙方訊息都存進 `tutor_messages`。不呼叫 `chat.configure`，所以不改筆記本本身的對話設定。
- **不做**：
  - PPTX 檢視：目前流程只註冊 PDF 講義；PPTX 要先轉成 PDF 才會進入課程。
  - 開網頁就自動全螢幕：瀏覽器不允許。改由 `scripts/launch_app.sh` 以 Chrome App 模式全螢幕開啟。

## 4. 介面 / API

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET/HEAD | `/api/courses/{code}/lectures/{n}/source.pdf` | 講義 PDF（inline）；路徑超出課程資料夾回 403 |
| GET | `/api/courses/{code}/lectures/{n}/key-points` | 已存的重點 |
| POST | `/api/courses/{code}/lectures/{n}/key-points` | 產生重點（`{"force": false}`） |
| GET | `/api/courses/{code}/study/memory` | 記憶強度、連續天數、熱力圖 |
| GET/POST/DELETE | `/api/courses/{code}/study/tutor` | 家教對話（`lecture_no` 可省略，代表全課程） |
| POST | `/api/courses/{code}/study/quiz-attempts` | 每題錯題可帶 `confidence`；整份可帶 `confidence` 統計 |

MCP 工具：
- 唯讀：`get_key_points`、`get_memory_strength`
- 需要 `confirm=True`：`generate_key_points`、`ask_tutor`

## 5. 驗收標準

- `tests/test_learning.py`：重點 JSON 解析、PDF 只讀且不能超出資料夾、重點只問一次、家教延續同一段對話、記憶曲線與連續天數、信心評分存檔、MCP 寫入工具需要 confirm。
- 瀏覽器實測：
  - 重點標示涵蓋跨行連字號與頁碼差一頁的情況，跳頁位置正確，重點清單捲動時固定在畫面上。
  - 信心回饋、混合複習、上次停在都正常。
  - 375px 寬度下沒有任何元素超出畫面。

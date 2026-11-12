# ISSUE-037：課程代碼因學期前綴衝突導致覆寫舊課程並繼承舊筆記本

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-12
- **Agent**：`antigravity`
- **任務**：`TASK-020`

## 1. 現象

使用者在已有課程（如 `115-1 心理學研究法`）的系統中，新增另一門名稱完全不同的新課程（如 `115-1 生涯諮商`）時：
1. 系統沒有在 Google NotebookLM 開立新筆記本，而是直接把新課程的所有講義 PDF 全數上傳到**舊課程的 NotebookLM 筆記本**中，導致不同科目的資料混在一起。
2. 當使用者手動刪除舊課程後，再重新加入新課程，系統便恢復正常，成功在 NotebookLM 建立了新名稱的獨立筆記本（`[115-1] 生涯諮商`）。

- **錯誤訊息**：無拋出例外（靜默邏輯錯位）。系統日誌顯示：
  `Reusing Gemini Notebook notebook 04568153-2834-4884-b70a-6d4fc6e874d9 for 115-1`
  （`04568153` 原為心理學研究法的 notebook，卻被綁給了生涯諮商）
- **重現步驟**：
  1. 建立資料夾 `115-1 心理學研究法` 並加入課程，系統在 NotebookLM 建立筆記本 A（`notebook_id = A`）。
  2. 建立資料夾 `115-1 生涯諮商` 並加入課程。
  3. 觀察 NotebookLM：發現講義被上傳至筆記本 A，沒有建立筆記本 B。
  4. 刪除課程 `115-1`，重新加入 `115-1 生涯諮商`，系統建立全新筆記本 B。
- **影響範圍**：
  - `services/course_parser.py`（資料夾名稱解析）
  - `adapters/db/repository.py`（`CourseRepository.save_course` 更新衝突邏輯）
  - `services/orchestrator.py`（`setup_notebook_and_sources` 筆記本關聯）
  - 所有以學期（如 `114-1`、`115-1`、`2026S`）為資料夾前綴的課程管理。

## 2. 根本原因

此問題是由**「資料夾代碼解析正則設計缺陷」**與**「資料庫以代碼為主鍵之盲目覆寫繼承」**共同交織產生的連鎖 Bug：

1. **資料夾正則解析代碼衝突（Code Collision）**：
   - 位於 `src/notebooklm_batch_studio/services/course_parser.py` 的 `parse_course_folder_name`：
     ```python
     match = re.match(r"^([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)[\s_]+(.+)$", clean_name)
     ```
   - 該正則假設前綴連字號字串（如 `BIO101` 或 `115-1`）一定是「唯一的課程代碼（Course Code）」。
   - 但在台灣或常見大學命名慣例中，`115-1` 是**「學期（Semester）」**而非課程代碼。
   - 結果：`115-1 心理學研究法` 與 `115-1 生涯諮商` 被解析出**完全相同**的課程代碼：`code = "115-1"`！

2. **資料庫以 `code` 作為主鍵，更新時繼承舊的 `notebook_id`**：
   - 在 `CourseRepository.save_course(course)` 中：
     ```python
     existing = self.session.get(CourseRecord, course.code)
     if existing is None:
         ...
     else:
         existing.name = course.name
         existing.source_dir = course.source_dir
         if course.notebook_id:
             existing.notebook_id = course.notebook_id
     ```
   - 當新課程 `115-1 生涯諮商` 傳入時，`existing` 查到了舊記錄 `115-1 心理學研究法`。
   - 由於新掃描的 `course.notebook_id` 初始為 `None`，`if course.notebook_id:` 為假，因此 `existing.notebook_id` **保留了舊課程的筆記本 ID（`04568153-...`）**！
   - 資料庫中的 `existing.name` 雖然被改成了「生涯諮商」，但其綁定的 `notebook_id` 依然指向「心理學研究法」。

3. **任務執行器跳過建立新筆記本，直接上傳講義至舊筆記本**：
   - 在 `orchestrator.py` 的 `setup_notebook_and_sources` 與 `_execute_job_internal` 中：
     ```python
     notebook_id = course.notebook_id
     if not notebook_id:
         # 只有在 notebook_id 為空時才會開立新筆記本
         notebook_id = await self.notebooklm_client.create_notebook(title)
     ```
   - 因為 `course.notebook_id` 已被繼承為舊筆記本，系統誤判「此課程已有筆記本」，直接使用舊 ID 呼叫 `upload_source(notebook_id, pdf)`，導致新課程的所有講義被直接注入舊筆記本中！

4. **刪除舊課程後為何「恢復正常」**：
   - 當手動刪除舊課程後，資料庫中的 `115-1` 被清理。
   - 重新加入 `115-1 生涯諮商` 時，`existing is None`，系統視為全新記錄，`notebook_id` 初始為空，因而正確觸發了 `create_notebook("[115-1] 生涯諮商")`。

## 3. 修正或規避方式

需同時在解析層與資料庫儲存層進行防禦性修復：

1. **防重名與多重前綴解析（`course_parser.py`）**：
   - 如果資料夾名稱同時包含學期與課程代碼（如 `115-1_CS101_演算法`）或純學期（如 `115-1 心理學研究法`），單純以第一個連字號判定代碼過於脆弱。
   - 若代碼全由純數字加連字號組成（如 `115-1`），應視為學期前綴，真正的代碼應結合後續名稱或由使用者自訂，例如 `115-1_心理學研究法` 或 `115-1-PSYCH`。
2. **資料庫儲存衝突判定（`CourseRepository.save_course`）**：
   - 檢查 `course.code` 衝突：當 `existing` 存在時，比對 `existing.name` 與 `course.name`。
   - 若 `existing.name != course.name` 且兩者來源路徑 `source_dir` 不同，代表這是**兩門不同課程代碼碰撞（Collision）**，嚴禁靜默覆寫並繼承 `notebook_id`！應拋出 `DuplicateCourseCodeError` 或自動為新課程附加後綴（如 `115-1_2`），或要求使用者確認。
   - 若判定為課程更名或重掃描，若更換了 `source_dir`，不可直接沿用舊的 `notebook_id`。
3. **相關程式碼註解加 `Refs: ISSUE-037`**。

## 4. 防回歸測試

1. 在 `tests/test_course_reregistration.py` 或 `tests/test_course_admin.py` 中新增：
   - `test_different_course_same_code_does_not_inherit_notebook_id`：模擬先註冊 `115-1 心理學研究法`（產生 `nb_1`），再註冊 `115-1 生涯諮商`，驗證系統拒絕覆寫或正確區隔，絕不將 `nb_1` 指派給生涯諮商。
   - `test_semester_prefixed_folder_parsing`：驗證學期前綴資料夾（如 `115-1 生涯諮商` 與 `115-1 心理學研究法`）的代碼生成不會撞名。

# ISSUE-069：遷移學習資料夾會把已在 study/ 的校方命名課程搬到純課名資料夾

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-25
- **Agent**：`claude-code`
- **任務**：`-`

## 1. 現象

在真實資料上預覽 POST /api/courses/migrate-study-layout（dry_run=true）時，115-1_CP30210 與 115-1_GC68210 顯示 planned，目標為 study/115-1/心理學研究法 與 study/115-1/和 AI 一起寫程式；若實際執行（網頁 API 或 MCP migrate_study_layout confirm=True），會把課程搬離校方命名的 CP__30210-… / GC__68210-… 資料夾。115-1_CP31000 只因 subject 剛好等於資料夾名稱而未受影響。

- **錯誤訊息**：沒有錯誤；dry-run 回傳 `115-1_CP30210 planned → study/115-1/心理學研究法`、`115-1_GC68210 planned → study/115-1/和 AI 一起寫程式`。
- **重現步驟**：
  1. 以 record-only 登錄或整併一門位於 `study/115-1/CP__30210-心理學研究法/` 的課程（`subject=心理學研究法`）。
  2. 呼叫 `POST /api/courses/migrate-study-layout`，body `{"dry_run": true}`。
  3. 該課程顯示 `planned`，目標為不含課號前綴的資料夾。
- **影響範圍**：`services/study_migration.py::_migrate_one_course`（HTTP `migrate_study_layout`、MCP `migrate_study_layout`）與 `services/legacy_consolidation_ops.py::apply_folder_rename_step`。真實資料未被搬動（只執行過 dry-run）。

## 2. 根本原因

study_migration._migrate_one_course 一律用 resolve_course_study_dir(term, subject) 重新計算目標路徑，只有計算結果剛好等於現有 study_dir 才略過；而 record-only 登錄把 subject 設為課名、legacy_consolidation_ops.apply_folder_rename_step 卻把 subject 設為完整資料夾名稱，兩者不一致，導致已在 study/ 底下的課程被判定為需要搬移。

## 3. 修正或規避方式

study_migration 新增 _is_inside_study_root：課程 study_dir 已是 study_root_dir 底下的既有資料夾時直接回傳 already_migrated，不搬移、不改 DB；apply_folder_rename_step 改以 parse_course_folder 解析出的課名（例如 生涯諮商與實務）寫入 subject。真實資料預覽三門課皆為 already_migrated。（相關程式碼註解加 `Refs: ISSUE-069`）

## 4. 防回歸

tests/test_literature_and_hierarchy.py::StudyHierarchyAndMigrationTest::test_migration_leaves_courses_already_in_study_root_alone；tests/test_legacy_consolidation.py 改為斷言 subject == 生涯諮商與實務。

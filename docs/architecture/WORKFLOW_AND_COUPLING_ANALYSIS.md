# 系統工作流、架構糾纏與程式碼符合度分析報告

> 本報告基於 `graphify` 知識圖譜分析結果（`graphify-out/GRAPH_REPORT.md`）、端到端工作流程規格書（[`SPEC-010`](../specs/010-user-end-to-end-workflow.md)）以及核心原始碼（`src/notebooklm_batch_studio/`）之交叉比對，全面診斷系統糾纏點、程式與工作流的落差，並提供具體的梳理與解耦藍圖。

---

## 1. Graphify 知識圖譜解析

### 1.1 圖譜拓撲概況
- **規模統計（已套用 `.graphifyignore` 排除第三方雜訊，commit `c9305b1e`）**：**4,671** 個節點、**9,409** 條邊、**283** 個社群（311 個檔案 · ~304,918 字；`agentctl graph` AST 依賴圖為 139 個模組、417 條依賴邊）。
- **循環依賴（Import Cycles）**：**0（無）**。後端 Python 嚴格遵守了 `entrypoints ➔ adapters ➔ services ➔ domain ➔ config` 的單向分層架構。
- **噪聲過濾（Vendor Noise）**：
  - 過濾前原圖譜達 9,270 個節點、18,667 條邊、392 個社群；透過 `.graphifyignore` 排除 `entrypoints/static/vendor/`（PDF.js、Lucide、字型等第三方靜態檔案）後，成功剔除 **4,762** 個第三方無關節點（如 `XFAObject`、`AnnotationEditor`、`CanvasGraphics` 等）。
  - **解讀結論**：底層 PDF 閱讀器屬於自包含的第三方靜態工具，排除後已清晰浮現本專案自研的領域核心與前端黏合代碼。

### 1.2 核心業務 God Nodes（超高連接度中樞）
排除第三方函式庫後，`graphify-out/GRAPH_REPORT.md` 顯示專案真實的核心樞紐（前 10 大 God Nodes）為：
1. **`BatchStudioService` (142 邊)**：位於 `services/orchestrator.py`，是全系統最大的中心外觀（Facade），幾乎所有業務流均需穿透此類別。
2. **`AppConfig` (113 邊)**：位於 `config/settings.py`，集中式設定，注入所有服務層。
3. **`Course` (108 邊)**：位於 `domain/models.py`，核心領域實體，貫穿所有資料庫儲存、設定解析、任務排程與前端展示。
4. **`ArtifactJob` (96 邊)**、`QueueRepository` (81 邊)、`ArtifactType` (77 邊)、`CourseRepository` (76 邊)、`Lecture` (62 邊)、`GenerationOptions` (56 邊)、`CourseNotFoundError` (53 邊)：構成批次排程與領域模型的骨幹。
5. **前端中樞 `studio-app.js` 與 `studio-batch.js`**：控制整體介面切換、狀態輪詢與研讀台聯動。

---

## 2. 系統糾纏點深度診斷 (Entanglements & Coupling)

透過知識圖譜社群邊緣度與原始碼檢視，發現系統目前存在四大關鍵糾纏點：

```
┌────────────────────────────────────────────────────────────────────────┐
│                        四大系統糾纏點架構圖                             │
├────────────────────────────────────────────────────────────────────────┤
│ 1. 後端 God Service 糾纏                                               │
│    BatchStudioService 承擔過多異質職責 (CRUD + 佇列 + 同步 + 轉檔 + 報表) │
├────────────────────────────────────────────────────────────────────────┤
│ 2. 前端全域狀態隱式耦合 (Spaghetti Coupling)                           │
│    12 個 JS 檔共享 window 命名空間，無 State Store / EventBus，互相調用 │
├────────────────────────────────────────────────────────────────────────┤
│ 3. 任務規劃 (Planning) 與執行線程池 (Execution) 混雜                     │
│    generate_jobs_for_course 混在 worker_pool.py 內部                   │
├────────────────────────────────────────────────────────────────────────┤
│ 4. 記憶體狀態 vs 資料庫狀態雙軌失步                                    │
│    WorkerPool.blocked_quota_types (記憶體) vs QUOTA_WAIT (DB) 脫節     │
└────────────────────────────────────────────────────────────────────────┘
```

### 糾纏點 1：後端 `BatchStudioService` 職責膨脹（巨型外觀 God Service）
- **現象**：`orchestrator.py` 的 `BatchStudioService` 達 767 行，同時承擔了：
  1. 課程註冊、資料夾掃描、課件解析 (`CourseParser`)
  2. 任務矩陣生成與佇列推播 (`QueueRepository`)
  3. WorkerPool 背景生命週期維護 (`start`, `stop`, `pause`, `resume`)
  4. 雲端雙向同步與 Source ID 校驗 (`RemoteSyncService`, `NotebookLMAdapter`)
  5. 12 種產出轉檔、下載、修補與重試 (`ArtifactRunner`, `quiz_reader`)
  6. 進度統計與儀表板摘要 (`CourseReporter`)
- **風險**：任何一處業務變更（如修改進度計算公式、增加新的雲端同步機制）都必須修改此類別，違反單一職責原則（SRP），並容易引發回歸錯誤。

### 糾纏點 2：前端 12 個無模組化腳本之全域變數與隱式事件耦合（最具風險之糾纏）
- **現象**：
  - `index.html` 依序引用 12 個腳本（`studio-core.js` ➔ `studio-app.js` ➔ `studio-batch.js` ➔ `studio-settings.js` ➔ `studio.js` ➔ `studio-learning.js` ➔ `studio-shell.js` ➔ `studio-player.js` ➔ `studio-bench.js` ➔ `studio-fonts.js` ➔ `studio-focus.js` ➔ `studio-start.js`）。
  - 各模組之間**沒有使用 ES Module 的 `import`/`export`**，全數將資料掛載於全域 `window`（如 `window.currentCoursesList`, `window.currentStudyCourse`, `window.activeStudyLectureNo`, `window.allJobsCache`）。
  - 當某模組執行動作時，直接隨機呼叫其他模組的全域函式（例如在 `studio-batch.js` 裡呼叫 `fetchCourses()`、在 `studio-app.js` 裡呼叫 `renderWorkbench()`、在 `studio-start.js` 設置定時輪詢）。
- **後果（已引發之 Bug）**：
  - **`ISSUE-034`**：`studio-batch.js` 刪除了課程，但 `studio-app.js` 與 `studio-bench.js` 的 `currentStudyCourse` 與 DOM 元素未被通知清空，造成研讀工作室仍顯示舊課程名稱與畫面殘留。
  - **`ISSUE-036`**：`studio-start.js` 定時器輪詢時僅呼叫了 `fetchStatus()`，忘記呼叫 `fetchCourses()`，造成前台整體進度條無法自動更新。

### 糾纏點 3：任務規劃（Planning）與任務執行（Execution）混雜
- **現象**：`generate_jobs_for_course`（根據課程 Profile、自訂勾選、客製 Prompt 生成任務矩陣的排程規則）被放置於 `services/worker_pool.py` 中。
- **風險**：`WorkerPool` 應純粹是非同步工作線程池（管理 Consumer Loop、併發數、退避策略）；將 Producer/Planner 邏輯塞在 Consumer 模組中，導致排程規則與線程調度緊密耦合。

### 糾纏點 4：記憶體狀態與 SQLite 資料庫狀態雙軌判定（State Desynchronization）
- **現象**：
  - `WorkerPool.blocked_quota_types` 屬於服務記憶體狀態（`set[ArtifactType]`）。
  - 資料庫任務狀態為 `JobStatus.QUOTA_WAIT`。
  - 當系統被使用者暫停、手動重試任務，或課程被刪除時，記憶體中的集合未被同步清空，而背景 probe loop 又因資料庫中已無 `QUOTA_WAIT` 任務而無法自動解鎖，導致佇列永久卡死（`ISSUE-035`）。
- **風險**：記憶體狀態與持久化資料庫狀態脫鉤，無法達成崩潰自癒（Crash Resilience）。

---

## 3. 工作流程與程式碼符合度比對 (Workflow Spec vs Code Conformance)

對照規格書 [`docs/specs/010-user-end-to-end-workflow.md`](../specs/010-user-end-to-end-workflow.md) 的 8 大階段，檢查實際程式碼的符合度：

| 階段 | 規格書要求 | 程式碼實際狀態 | 符合度判定 | 落差與問題說明 |
|---|---|---|:---:|---|
| **階段 1：首頁與環境準備** | 綁定 `127.0.0.1:8768`，支援 Tailscale 遠端存取與主機健康度檢查 | `api.py` 透過 `HostValidationMiddleware` 支援設定檔之 `HTTP_ALLOWED_HOSTS` 與 `HTTP_ALLOWED_ORIGINS` | ✅ **完全符合** | 通過 Tailscale 驗證。 |
| **階段 2：建立/匯入課程與檔案** | 本機檔案夾掃描、PDF 數量計算、課程名稱與講次解析、防呆檔名與防撞碼提示 | `folder_browser.py` 實作安全目錄瀏覽；`course_parser.py` 與 `CourseRepository.save_course` 已於 `TASK-020` 修正學期前綴撞碼與誤繼承 `notebook_id`（`ISSUE-037`） | ✅ **完全符合** | 支援自動建立 TOML、PDF 去重與學期前綴資料夾防撞碼。 |
| **階段 3：產出參數與自訂偏好** | 支援三層階層式繼承（系統預設 ➔ 課程自訂 ➔ 12 項產出個別設定），Prompt 覆寫 | `course_settings.py` 實作階層合併邏輯，支援每項產出獨立參數 | ✅ **完全符合** | 測試案例完整覆蓋。 |
| **階段 4：排程生成與狀態輪詢** | 1. 併發 2~3 Worker<br>2. 額度冷卻退避與自動/手動立即喚醒<br>3. 即時推進整門課與講次進度條<br>4. 分母排除 skipped 任務 | 1. `WorkerPool` 實作並發處理<br>2. `ISSUE-035`：`WorkerPool.resume()` 與 probe loop 清空封鎖集合且 `force=True` 喚醒<br>3. `ISSUE-036`：`syncLiveCourseProgress` 連動更新 `fetchCourses()` 與 `currentStudyCourse`<br>4. `ISSUE-036`：`orchestrator` 與前端皆排除 `skipped` | ✅ **完全符合** | 已解決並納入 `tests/test_quota_and_limits.py` 與 `tests/test_dummy_user_simulation.py` 回歸保護。 |
| **階段 5：研讀工作室** | 課程目錄切換、音檔播放、PDF 雙欄標註、AI 家教對話、課程刪除後乾淨歸零 | 1. 播放器、PDF 標註與學習總覽正常運作<br>2. `ISSUE-034`：刪除課程時後端清除關聯表，前端透過 `clearCoursePreferences(code)` 與 `initStudyPortal()` 乾淨歸零 | ✅ **完全符合** | 已解決並納入 `tests/test_course_admin.py` 與 `tests/test_dummy_user_simulation.py`。 |
| **階段 6：自主學習與評量** | 30 題隨堂測驗、3D 卡牌、錯題本收錄、間隔重複演算法 | `learning_service.py` 與 `study_service.py` 完整實作記憶衰減模型與錯題累計 | ✅ **完全符合** | 測試案例完整覆蓋。 |
| **階段 7：匯出與下載** | 支援 Markdown、HTML、Quiz 題庫、SVG/Mermaid 心智圖、Anki CSV 匯出 | 下載路由與轉檔服務完整支援單檔與 Anki CSV 匯出 | ✅ **完全符合** | 測試皆通過。 |
| **階段 8：例外處理與維護管理** | 1. 刪除課程 100% 清理關聯 DB 表與 UI 偏好，產出移至 `deleted/` 備份<br>2. 離線小白使用者混沌測試防呆 | 1. `ISSUE-034`：完整清除 `key_points`、`tutor_messages` 與 `ui_preferences`<br>2. `TASK-017`：`tests/test_dummy_user_simulation.py` 完整驗證全流程防呆與靜態不變量 | ✅ **完全符合** | `193` 項測試（含全流程模擬與 UI 結構回歸）全部通過。 |

---

## 4. 工作流程梳理與架構解耦優化方案

針對上述診斷出的糾纏點與落差，提出以下四項梳理與解耦改善藍圖：

### 4.1 前端微型狀態中心與事件匯流排（解耦前端 12 個腳本）
在 `studio-core.js` 引入極簡的 Publish/Subscribe 事件中心與反應式狀態管理（無需依賴外部龐大庫）：

```javascript
// studio-core.js (EventBus & State Store)
window.StudioBus = {
  events: {},
  on(event, callback) {
    (this.events[event] = this.events[event] || []).push(callback);
  },
  emit(event, data) {
    (this.events[event] || []).forEach(cb => cb(data));
  }
};

window.StudioStore = {
  state: {
    currentCourse: null,
    coursesList: [],
    queueCounts: {}
  },
  setCourses(list) {
    this.state.coursesList = list;
    StudioBus.emit('courses:updated', list);
  },
  resetCourse(code) {
    if (this.state.currentCourse === code) {
      this.state.currentCourse = null;
      StudioBus.emit('course:cleared');
    }
  }
};
```
- **解耦效果**：
  - 當 `studio-batch.js` 刪除課程時，只需發布 `StudioBus.emit('course:deleted', code)`。
  - `studio-app.js`（研讀中樞）、`studio-bench.js`（工作台）、`studio-player.js`（播放器）各自監聽此事件並清空 DOM，徹底根治 `ISSUE-034`。
  - 當定時輪詢獲取最新進度時，發布 `queue:updated`，所有需要進度的組件自動刷新，徹底根治 `ISSUE-036`。

### 4.2 後端職責拆分（拆解 `BatchStudioService`）
將 `BatchStudioService` 拆分為三個專職子協調器：
1. **`CourseLifecycleService`**：負責課程資料夾掃描、註冊、元資料維護、安全刪除與備份移轉。
2. **`GenerationOrchestrator`**：負責任務規劃（`JobPlanner`）、WorkerPool 啟動/暫停/恢復、額度監控與佇列進度。
3. **`ArtifactExportService`**：負責檔案轉檔、重命名校驗、下載打包與 Anki 匯出。
- **解耦效果**：減少 `orchestrator.py` 單檔負擔，降解 God Node 的連接度。

### 4.3 任務規劃與執行池物理拆分
- 將 `generate_jobs_for_course` 從 `worker_pool.py` 移出至 `services/job_planner.py` 或 `services/quota_planner.py`。
- `WorkerPool` 僅依賴 `QueueRepositoryProtocol` 與 `JobExecutor`，維持高度正交性與獨立可測試性。

### 4.4 狀態單一真實來源（Single Source of Truth, SSOT）
- **額度封鎖解鎖**：廢除記憶體中獨立且容易脫節的 `blocked_quota_types` 判定，改為以「資料庫中是否存在狀態為 `QUOTA_WAIT` 且冷卻時間大於當前時間的任務」作為唯一判定基準；手動重試或恢復時統一清除冷卻戳記。
- **進度百分比統一**：前後端統一公式為：
  $$\text{進度} = \frac{\text{DONE}}{\text{TOTAL} - \text{SKIPPED}} \times 100\%$$
  後端計算完成後直接提供 `progress_percent`，前端僅負責呈現，避免前後端計算分歧。

---

## 5. 執行計畫關聯矩陣

本報告診斷出之落差與梳理項目，均已建立對應的任務卡，推薦後續依序落地實作：

| 改善項目 | 涉及糾纏點 / 落差 | 對應任務卡 | 狀態與預期成效 |
|---|---|---|---|
| **防學期前綴撞碼覆寫舊筆記本** | 階段 2 資料夾解析與 DB 覆寫風險 (`ISSUE-037`) | `TASK-020` | ✅ **已完成**：純數字/學期前綴保留完整資料夾名為 `code`，且不同 `name` + `source_dir` 碰撞時不繼承舊 `notebook_id` |
| **課程目錄研讀進度篩選器** | v05 介面遷移功能缺口 | `TASK-012` | ✅ **已完成**：實作「全部 / 進行中 / 已完成」篩選與偏好記憶 |
| **套用課程設定至其他課程** | v05 介面遷移功能缺口 | `TASK-013` | ✅ **已完成**：實作批次複製 `GenerationOptions`、語言與模擬考題數之 Service、API、MCP (`confirm`) 與對話框 |
| **修復課程刪除殘留** | 糾纏點 2、階段 5/8 落差 (`ISSUE-034`) | `TASK-014` | ✅ **已完成**：後端補刪 3 張關聯表記錄，前端清空全域狀態、偏好快取與研讀台 DOM |
| **修復 WorkerPool 額度卡死** | 糾纏點 4、階段 4 落差 (`ISSUE-035`) | `TASK-015` | ✅ **已完成**：`resume()` 與 probe loop 同步解除額度封鎖，`force=True` 支援手動喚醒 |
| **修復總進度即時推進** | 糾纏點 2、階段 4 落差 (`ISSUE-036`) | `TASK-016` | ✅ **已完成**：輪詢補齊課程刷新並排除 skipped 任務，進度條正確抵達 100% |
| **愚蠢使用者全流程混沌測試** | 階段 8 維護防呆與既有 UI 問題實證補測 | `TASK-017` | ✅ **已完成**：`tests/test_dummy_user_simulation.py` 覆蓋離線全流程操作與靜態不變量檢查 |
| **前端狀態與後端協調器解耦** | 糾纏點 1、2、3（架構優化） | `TASK-018` | ✅ **已完成**：導入 `StudioBus`/`StudioStore`，拆分 `course_onboarding.py`、`job_planner.py`、`quiz_runner.py`、`sync_service.py`、`mcp_studio_tools.py` 及 5 個前端輔助模組 |
| **全量 Resolved 問題實證覆核** | 假性/無自動化測試保護之歷史問題清查 | `TASK-019` | ✅ **已完成**：剔除第三方圖譜噪聲、解決 `ISSUE-034~036` 並納入自動化測試驗收 |
| **Code Review Guard 既有債清理** | 核心鐵律 15（零忽視即時修復） | 全庫重構 | ✅ **已清零**：所有 `.py`/`.js` 符合檔案/函式長度、參數與巢狀限制，執行 `review_guard.py` 達 `0` CRITICAL、`0` IMPORTANT |

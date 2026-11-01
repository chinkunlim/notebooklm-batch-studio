# SPEC-009: 研讀工作室與學生工作台介面重構與外觀自訂規格書 (Claude Handoff)

> **目標讀者**：Claude Code 與後續接手開發者  
> **建立時間**：2026-11-02  
> **前置狀態**：已在原型 `mockups_gallery.html` 與 `designs_archive/` 完成 4 個世代的原型探索與驗證；使用者確認本規格書後由 Claude Code 統一落實回正式代碼庫。  
> **核心原則**：**程式碼未經使用者明確指示不私自修改**；依本規格書與既有原型進行精確、穩健的代碼實作。

---

## 1. 使用者核心反饋與既有共識 (Design Decisions & User Directives)

### 1.1 使用者高度確認與喜愛的資產 (MUST PRESERVE)
- **奢華黑膠唱機效果 (The Deluxe Turntable)**：
  - 使用者明確反饋：**「最後一個版本的黑膠唱片效果很不錯」**。
  - **盤面工藝**：採用 `conic-gradient` 呈現 4 象限十字光澤流轉（非均向性反射 Anisotropic Sheen）與微音軌溝槽（Micro-grooves），杜絕塑膠感。
  - **機械唱臂物理動態 (Tonearm Assembly)**：位於右上角，播放時優雅下旋 24° 落針至音軌；暫停時平滑回彈 -6° 歸位至停放支架。
  - **270° 環形進度弧線軌道 (Arc Scrubber)**：圍繞黑膠外緣的弧形軌道與發光刻度微珠（Luminous Progress Bead），模擬鐘錶錶盤向心時間感知。
  - **中央講義封面視覺錨點 (Center Artwork Core)**：圓心不放易致暈眩的旋轉文字，而是圓形遮罩的講義核心圖解（神經突觸與動作電位）＋高光金屬內圈。
  - **4 款聲學可視化庫 (Visualizer Skins)**：典雅黑膠、多重諧波 Sin 弦波、天體環形頻譜、專業矩陣 LED 聲譜柱。

---

### 1.2 使用者嚴厲指正之痛點與修正規範 (MUST FIX)

#### 痛點 1：文字全面去雜訊化（Text-First & Anti-Emoji）
- **使用者要求**：**「不要一直跟我用icon，那個設計與自訂，為什麼有一個調色盤的icon？！」**
- **修正規範**：
  - 頂部分段標籤列徹底去除任何 Emoji 或突兀圖標，回歸極簡、大器的高級排版：
    `研讀總覽` | `研讀工作室` | `弱點複習` | `批次排程` | `設計與自訂`
  - 嚴格禁止在按鈕或標題上隨意添加 `🎨`、`☀️`、`🌙` 等裝飾性符號。
  - 日夜模式按鈕使用乾淨文字：`日光` / `暗夜`。

#### 痛點 2：圖標導入規範（No Hand-Drawn Awkward SVGs）
- **使用者要求**：**「你需要的icon，可以用css import進來的方式，不一定要自己畫，畫了又不倫不類！」**
- **修正規範**：
  - 透過標準 CDN 引入 Lucide Icons 或使用標準字型庫：
    ```html
    <link rel="stylesheet" href="https://unpkg.com/lucide-static@0.344.0/font/lucide.css" />
    ```
  - 圖標一律維持統一的 1.75px 細線線條粗細，大小控制在 18x18px 或 20x20px，杜絕比例怪異的手繪路徑。

#### 痛點 3：左側微型 Dock 與滑動框背景
- **使用者要求**：**「那個左側icon選擇時的背景，我只是叫你把animation改成滑動，為什麼連設計都變了？」**
- **修正規範**：
  - 左側 Dock **維持原始 4 個純粹微型圖標**（移除多餘的第 5 個調色盤圖標）：
    1. 首頁 / 總覽 (`icon-home` / Home)
    2. 研讀工作室 (`icon-book-open` / Book)
    3. 弱點錯題集（**圓圈中問號** `icon-help-circle` / Circle-Help）
    4. 批次排程佇列 (`icon-clock` / Clock)
  - **滑動框背景 (`.dock-slider-box-indicator`)**：
    - 維持原本圓角卡片半透明底色＋左側強調邊條設計。
    - 過渡動畫還原為純粹的**物理平移滑動**：
      `transition: transform 0.32s cubic-bezier(0.16, 1, 0.3, 1);`
      - 桌面端：`transform: translateY(${index * 56}px)`
      - 手機端：`transform: translateX(${index * 42}px)`

#### 痛點 4：知識產出物工作台解除強制三階分層
- **使用者要求**：**「Gemini 知識產出物工作台的架構採用三節分層，看起來很不方便，要一直切換。都要給我自行搭配」**
- **修正規範**：
  - **預設架構**：採用**全景平鋪九宮格矩陣 (9-Tool Overview Grid)**，全部 9 項產出物（PDF、語音、指南、心智圖、資訊圖表、簡報、數據表、30題測驗、3D抽認卡）一次整齊平鋪在卡片中，**點選任何一項直接在下方展開對應內容，無需在分頁間反覆切換！**
  - **多態自選**：在「設計與自訂」分頁中，保留讓使用者切換為：
    1. `matrix`：全景平鋪九宮格矩陣 (預設)
    2. `vertical-dock`：左側垂直工具羅盤
    3. `pinned`：常用釘選列
    4. `triad`：認知三階分層

#### 痛點 5：頂部導航新增第 4 主分頁「設計與自訂」
- **使用者要求**：**「增加一個選項在批次排程右邊，讓user可以customize主題、顯示等設計。跟現在的其他按鈕一樣」**
- **修正規範**：
  - 在 `.segmented-nav-track` 中於「批次排程」右側新增第 5 個標籤按鈕 `設計與自訂`。
  - 點擊同級切換至 `<section id="viewCustomize">`，內含：
    1. 個人頭像與左上角圖標設置
    2. 知識產出物工作台架構選擇
    3. 4 組成對亮暗固定配色切換
    4. 聲學可視化風格切換

#### 痛點 6：全設備 RWD 根治（自動垂直重排與等比縮放）
- **使用者要求**：**「現在整個rwb很糟糕！！！不會重新排列、縮放」**
- **根因分析**：
  - 先前媒體查詢僅監聽瀏覽器視窗 `@media (max-width: 500px)`，在桌面點擊「iPhone (416)」時，外層容器雖然縮小至 416px，卻未觸發手機 CSS 規則，導致桌面橫向三欄硬擠進 416px 產生溢出與排版錯亂。
- **修正規範**：
  - 所有響應式樣式必須同時綁定容器屬性與媒體查詢：
    `@media (max-width: 680px), [data-device="iphone"]`
  - **手機端具體行為**：
    - 主外框轉為單欄垂直流向 (`flex-direction: column !important; width: 100% !important;`)
    - 左側 Dock 轉為頂部橫條，滑動框改為水平位移
    - 頂部導航分段列支援觸控左右平滑滑動 (`overflow-x: auto; scrollbar-width: none;`)
    - 黑膠唱盤自動縮放至手機直徑（約 136px，弧形軌道 `scale(0.88)`），觸感按鈕自動換行置中，**杜絕任何右側溢出與橫向捲軸**。

#### 痛點 7：左上角個人頭像自訂
- **使用者要求**：**「左上角的icon，可以讓使用者自訂義，甚至放自己的頭像。都唷」**
- **修正規範**：
  - 支援點擊左上角圖標或在自訂頁面中：
    1. 上傳本機圖片（`FileReader.readAsDataURL` 即時轉為圓形頭像）
    2. 輸入 1~3 字縮寫（如 `LK` / `AI`），動態生成字母徽章
    3. 挑選 6 款預設學術圖標（博士帽、大腦、書卷、星芒、徽章、預設 G）

---

## 2. 歷史原型與歸檔檔案地圖 (Artifacts & Historical Archives)

所有探索過程中的獨立完整原型均已歸檔在以下路徑，供 Claude 直接比對參考：

| 版本檔案 | 路徑 | 說明 |
|---|---|---|
| **Version 1** | `designs_archive/version_01_classic_triptych.html` | 原始三欄經典排程儀表板。 |
| **Version 2** | `designs_archive/version_02_dual_column_sanctuary.html` | 心流雙欄研讀室（50/50 閱讀比例）。 |
| **Version 3** | `designs_archive/version_03_luxury_turntable_visualizer.html` | **（使用者高度好評）** 奢華黑膠唱機、機械唱臂、環形進度弧線與 4 款畫布。 |
| **Version 4** | `designs_archive/version_04_workbench_customizer.html` | 全景九宮格＋自訂主分頁＋全設備 RWD＋個人頭像完整實作。 |
| **總展間** | `mockups_gallery.html` | 當前主展示檔案，整合上述所有功能。 |
| **索引手冊** | `designs_archive/INDEX.md` | 詳細版本對照與代碼說明手冊。 |

---

## 3. 正式代碼庫落實路徑指引 (Claude Code Action Plan)

當使用者指示正式套用至專案代碼庫時，請 Claude Code 依循以下分層進行安全代碼移植：

1. **HTML 入口** (`src/notebooklm_batch_studio/entrypoints/static/index.html`):
   - 頂部導航新增 `<button class="seg-tab-btn" onclick="switchNav(4)">設計與自訂</button>`
   - 插入 `<section class="platform-view-stage" id="viewCustomize">`
   - 將產出物工作台改為 `<div class="tools-overview-matrix-grid" id="containerMatrixArch">` 支援九宮格平鋪
   - 引入 Lucide CSS CDN
2. **CSS 樣式層** (`src/notebooklm_batch_studio/entrypoints/static/studio.css` & `studio-theme.css`):
   - 移植奢華黑膠唱機樣式（非均向性光澤 `conic-gradient`、機械唱臂落針動態、270° 環形進度弧線、輕擬態按鍵槽）
   - 移植全設備 RWD 規則（綁定 `@media (max-width: 680px), [data-device="iphone"]`）
   - 移植九宮格卡片樣式與自訂控制台網格
3. **JS 互動邏輯層** (`src/notebooklm_batch_studio/entrypoints/static/studio.js` & `studio-learning.js`):
   - 更新 `switchNav(index)` 支援 5 個主要視圖
   - 移植黑膠唱臂落針控制 `togglePlayState()` 與環形進度弧線同步 `jumpAudio()`
   - 移植 3 種畫布渲染動態（Sin 弦波、天體環形頻譜、矩陣 LED）
   - 移植頭像與縮寫自訂函數（`applyAvatarImageSrc`, `onInitialsChange`, `setPresetAvatar`）

---

## 4. 品質保證與驗收清單

- [ ] **設計心理學審查**：執行 `python3 .agents/skills/design-psychology-master/scripts/design_audit.py`，分數維持 100/100。
- [ ] **單元測試全數通過**：執行 `uv run python -m unittest discover -s tests -v`，173 項測試 100% 通過。
- [ ] **文字去雜訊**：頂部導航為純文字排版，無任何 emoji 或多餘裝飾圖標。
- [ ] **左側 Dock 原貌**：維持 4 個標準圖標（首頁、書卷、圓圈問號、時鐘），滑動框僅使用垂直/水平物理平移。
- [ ] **全設備 RWD**：桌面點選「iPhone (416)」時，App 自動單欄垂直重排、黑膠唱盤等比縮小、無橫向溢出。
- [ ] **產出物九宮格**：9 項工具一次展現，點選直接展開內容，免反覆切換頁籤。

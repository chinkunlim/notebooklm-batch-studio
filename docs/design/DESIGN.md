# 設計版本對照清單 (DESIGN)

> 由 Antigravity 在 2026-11-02 產生，原本存在 Antigravity 自己的工作區；收尾時複製進專案，讓 Claude Code 與其他電腦都能讀到（SPEC-009、ADR-007 引用的就是這裡）。直接用瀏覽器打開 `.html` 檔即可檢視；`mockups_gallery.html` 是整合所有功能的總展示。


本目錄保存本專案歷次視覺設計與使用者體驗迭代之**完整、獨立 HTML 原型**。每個版本皆為自包含（Self-contained）檔案，可直接於瀏覽器開啟檢視，方便使用者與其他 AI Agent（如 Claude Code）隨時進行橫向對比、代碼調用與架構借鑑。

---

## 版本總覽對照表

| 版本編號 | 檔名 | 核心特色與架構 | 適用評估情境 |
|---|---|---|---|
| **Version 1** | [`version_01_classic_triptych.html`](version_01_classic_triptych.html) | **經典三欄排程儀表板**：原始批次生成管理首頁、三欄資訊羅列、緊湊功能列表。 | 評估原始工程化管理機能與批次排程佇列佈局。 |
| **Version 2** | [`version_02_dual_column_sanctuary.html`](version_02_dual_column_sanctuary.html) | **心流雙欄研讀室**：左文右視聽的 50/50 研讀比例、微型側邊圖標欄、三階認知分層。 | 評估大屏沉浸式長文閱讀與雙欄對照體驗。 |
| **Version 3** | [`version_03_luxury_turntable_visualizer.html`](version_03_luxury_turntable_visualizer.html) | **奢華黑膠唱機與 4 款聲學畫布**：非均向性反射黑膠盤面、金屬機械唱臂（播放落針/暫停抬升）、270° 環形進度弧線、輕擬態按鍵槽、Sin弦波/環形頻譜/矩陣LED切換。 | **（使用者高度好評）** 評估頂級擬態聲學留聲機與微儀式感。 |
| **Version 4** | [`version_04_workbench_customizer.html`](version_04_workbench_customizer.html) | **全景九宮格矩陣＋自訂主分頁＋全設備 RWD＋個人頭像**：<br>1. 9 大產出物一覽無遺免反覆切換；<br>2. 頂部導航批次排程右側新增獨立第 4 主分頁「🎨 設計與自訂」；<br>3. 根治 RWD（iPhone/iPad 模擬器與真機均能垂直重排與等比縮放）；<br>4. 左上角圖標支援個人圖片上傳、姓名縮寫與預設徽章。 | **當前最新旗艦版本**，整合所有最新反饋與自訂自由度。 |

---

## 各版本關鍵代碼與特性說明

### Version 3: 奢華黑膠唱機核心 (Turntable Engine)
- **非均向性反射**：`conic-gradient(from 0deg, #111412 0deg, #323b34 45deg, ...)` 呈現十字高光流轉。
- **唱臂物理可供性**：播放狀態 `turntableTonearm` 旋轉 24° 落針至音軌；暫停時平滑回彈 -6° 歸位。
- **270° 環形進度弧線**：SVG 圓弧配合 `stroke-dashoffset` 與發光刻度微珠（Luminous Bead），鐘錶空間感知。

### Version 4: 9 大產出物全景平鋪矩陣 (9-Tool Overview Grid)
- **免反覆切換**：原本需在「脈絡輸入」「結構提煉」「主動提取」三個分頁來回點擊，改為 3x3 響應式卡片矩陣平鋪，點選任何工具立即在下方展開舞台。
- **自選呈現架構**：可在自訂頁面自由切換為「全景九宮格」「垂直工具羅盤」「常用釘選列」「認知三階梯」。
- **全設備 RWD 根治**：樣式同時綁定 `@media (max-width: 680px), [data-device="iphone"]`，無論在桌面上點選 iPhone (416) 模擬器或真機訪問，皆自動切換為垂直單欄重排與元件縮放。

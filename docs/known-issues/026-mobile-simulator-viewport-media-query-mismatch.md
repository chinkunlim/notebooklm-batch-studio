# ISSUE-026：桌面環境切換手機模擬器時因視窗寬度未觸發 Media Query 導致排版與縮放失效

- **狀態**：🟢 已根治 (Resolved)
- **發現日期**：2026-11-02
- **Agent**：`antigravity`
- **任務**：`SPEC-009`

## 1. 現象

在桌面螢幕（視窗寬度 > 1200px）檢視互動展間或模擬器時，點擊「iPhone (416)」設備切換按鈕，畫面出現以下異常：
- 外層容器雖然被限制在 `max-width: 416px`，但內部佈局依然保持桌面橫向排版（如 3 欄並排、左側邊欄依然直立佔位）。
- 內容卡片嚴重擠壓、文字被裁切、黑膠唱盤未等比縮小、水平方向產生巨大的溢出與橫向捲軸。
- 使用者回饋：「不會重新排列、縮放」、「針對 rwb 的部分，iphone 的還是失敗的」。

## 2. 根本原因

CSS 媒體查詢 `@media (max-width: 500px)` 是**針對瀏覽器頂層視窗（Browser Viewport / window.innerWidth）進行條件比對**，而非針對局部容器（Container）。
當使用者在 1440px 寬度的桌面顯示器上點擊「iPhone (416)」時：
1. JavaScript 雖然替外層容器設定了 `data-device="iphone"` 並將寬度限縮為 416px；
2. 但瀏覽器視窗本體依然是 1440px，因此 `@media (max-width: 500px)` 內的所有手機專屬垂直重排與自適應樣式**完全不會被觸發**！
3. 容器內部被迫繼續執行桌面版 CSS（`flex-direction: row;`、3-column grid），導致嚴重破版與溢出。

## 3. 修正或規避方式

改採**雙軌驅動機制（Dual-Target Responsive Selectors）**，將所有手機自適應樣式同時綁定至媒體查詢與容器屬性：

```css
/* 同時涵蓋：真實手機視窗 (<= 680px) 與 桌面 iPhone 模擬器容器 ([data-device="iphone"]) */
@media (max-width: 680px), [data-device="iphone"] {
  .platform-app-frame {
    flex-direction: column !important;
    width: 100% !important;
  }
  .sidebar-icon-dock {
    width: 100% !important;
    height: 52px !important;
    flex-direction: row !important;
  }
  .studio-stage-container.mode-spread {
    display: flex !important;
    flex-direction: column !important;
  }
  .turntable-deck-chassis {
    flex-direction: column !important;
    align-items: center !important;
  }
  .turntable-orbit-wrap {
    transform: scale(0.88) !important;
  }
}
```

如此一來，無論是透過真實手機 Safari 開啟，還是在桌面以模擬器按鈕檢視，都能 100% 精確觸發垂直重組流向、唱盤等比縮放與零溢出排版。

## 4. 防回歸

1. 透過 `.agents/skills/design-psychology-master/scripts/design_audit.py` 驗收網格規範與 RWD 符合性。
2. 在 `docs/design/mockups_gallery.html` 頂部點擊「MacBook」「iPad」「iPhone」按鈕進行即時切換驗證，確保三種裝置尺寸均能流暢自適應。

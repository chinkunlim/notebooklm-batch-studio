# Lucide icon font（第三方，未修改）

- 套件：`lucide-static` 0.460.0（ISC 授權，見 `LICENSE`）
- 取得方式：在暫存資料夾執行 `pnpm add lucide-static@0.460.0`，複製 `font/lucide.woff2` 與 `font/lucide.css`；`lucide.css` 的 `@font-face` 改成只指向同資料夾的 `lucide.woff2`，檔案開頭加一行用途註解（其餘圖示規則不變）
- 用途：側欄、播放器、工作台等所有 `icon-*` 圖示；放在本機，離線也能顯示
- 升級：換版本後重新複製並改 `@font-face`，確認 `index.html` 用到的圖示名稱仍存在

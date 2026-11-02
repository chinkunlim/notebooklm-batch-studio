# 內建字型（第三方，未修改）

- 套件：`@fontsource-variable/noto-sans-tc` 5.3.1、`@fontsource-variable/noto-serif-tc` 5.3.1（Google，SIL Open Font License 1.1，見各資料夾的 `LICENSE`）
- 取得方式：在暫存資料夾執行 `pnpm add @fontsource-variable/noto-sans-tc @fontsource-variable/noto-serif-tc`，複製 `files/` 與 `index.css`（改名為 `noto-sans-tc.css` / `noto-serif-tc.css`，內容不變）
- 字型名稱：`Noto Sans TC Variable`、`Noto Serif TC Variable`（可變字重 100–900）
- 用途：網頁預設的內文與標題字型。檔案依 Unicode 範圍切成約 100 個小檔，瀏覽器只下載畫面上用到的字，離線也能顯示
- 使用者另外下載的 Google Fonts 不放這裡，存在 `DATA_DIR/fonts/`（見 ADR-009）

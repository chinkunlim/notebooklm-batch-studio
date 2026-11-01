# pdf.js（第三方，未修改）

- 套件：`pdfjs-dist` 4.10.38（Mozilla，Apache-2.0，授權見 `LICENSE`）
- 取得方式：在暫存資料夾執行 `pnpm add pdfjs-dist@4.10.38`，再複製 `build/pdf.min.mjs`、`build/pdf.worker.min.mjs` 這兩個檔案；`text_layer.css` 取自 `web/pdf_viewer.css` 中的 `.textLayer` 規則
- 用途：學習頁「📄 課件」分頁顯示講義 PDF，並在文字層標示 Gemini Notebook 挑出的重點
- 升級：換版本後重新複製這些檔案，並確認 `studio-reader.js` 的 `TextLayer` 用法仍相容

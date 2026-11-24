/* Gemini Notebook 學習工作室 — HTML / inline-handler escaping helpers shared by every page script.
   Loaded first, so escHtml and jsAttr are global before any renderer runs (Refs: ISSUE-046). */

/**
 * Escape text for safe insertion into HTML.
 * @param {*} s Any value
 * @returns {string} Escaped text ('' for null / undefined)
 */
function escHtml(s) {
  if (s === null || s === undefined) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

/**
 * Encode a value as a JavaScript string literal that is safe inside a double-quoted inline
 * handler attribute, e.g. onclick="openCourse(${jsAttr(code)})". escHtml alone is not enough
 * there: the browser decodes entities before running the handler, so a quote in AI-generated
 * text would end the JS string (Refs: ISSUE-046).
 * @param {*} value Value to pass as a string argument
 * @returns {string} HTML-escaped JSON string literal (with quotes)
 */
function jsAttr(value) {
  const literal = JSON.stringify(value === null || value === undefined ? '' : String(value));
  return literal
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

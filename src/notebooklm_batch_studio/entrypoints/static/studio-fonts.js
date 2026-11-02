/* Gemini Notebook 學習工作室 — font choice (設計與自訂 → 字型, ADR-009).
   Built-in Noto Sans / Serif TC (bundled in static/vendor, offline), the Mac's own PingFang / Songti,
   and Google Fonts the user downloads to this computer (GET / POST / DELETE /api/fonts). The choices
   are remembered preferences "fontBody" / "fontHead"; loaded after studio-shell.js (uses load, save). */

/** Fonts that need no download. */
const BUILTIN_FONTS = [
  { id: 'noto-sans', name: 'Noto Sans TC（內建）', stack: '"Noto Sans TC Variable", "PingFang TC", system-ui, sans-serif' },
  { id: 'noto-serif', name: 'Noto Serif TC（內建）', stack: '"Noto Serif TC Variable", "Songti TC", serif' },
  { id: 'mac-sans', name: '蘋方 PingFang TC（Mac 系統）', stack: '"PingFang TC", -apple-system, system-ui, sans-serif' },
  { id: 'mac-serif', name: '宋體 Songti TC（Mac 系統）', stack: '"Songti TC", "STSong", serif' },
];
let downloadedFonts = [];

/**
 * Read a remembered font choice.
 * @param {string} key "fontBody" or "fontHead"
 * @param {string} fallback Default choice id
 * @returns {{id: string, family?: string}} Choice
 */
function fontChoice(key, fallback) {
  try { const v = JSON.parse(load(key, 'null')); if (v && v.id) return v; } catch (e) { /* not set */ }
  return { id: fallback };
}

/**
 * CSS font-family list for a choice (downloaded fonts fall back to the built-in Noto).
 * @param {{id: string, family?: string}} choice Font choice
 * @returns {string} CSS font-family value
 */
function fontStack(choice) {
  const builtin = BUILTIN_FONTS.find(f => f.id === choice.id);
  if (builtin) return builtin.stack;
  return `"${String(choice.family || '').replace(/"/g, '')}", "Noto Sans TC Variable", "PingFang TC", sans-serif`;
}

/**
 * Load a downloaded font's stylesheet once (served from this computer, so it works offline).
 * @param {{id: string}} choice Font choice ("g:<slug>" for a downloaded font)
 */
function ensureFontCss(choice) {
  if (!choice.id.startsWith('g:')) return;
  const slug = choice.id.slice(2), id = `font-css-${slug}`;
  if (document.getElementById(id)) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet'; link.id = id; link.href = `/api/fonts/${encodeURIComponent(slug)}/font.css`;
  document.head.append(link);
}

/** Apply the remembered body and heading fonts to the page and show them in the 字型 card. */
function applyFontChoices() {
  const body = fontChoice('fontBody', 'noto-sans'), head = fontChoice('fontHead', 'auto');
  [body, head].forEach(ensureFontCss);
  root.style.setProperty('--font-sans', fontStack(body));
  // 跟著介面風格: headings use the body font, or Noto Serif in the 編輯典藏 style
  if (head.id === 'auto') root.style.removeProperty('--font-head'); else root.style.setProperty('--font-head', fontStack(head));
  renderFontControls();
}

/** Fill both font menus (built-in, Mac and downloaded fonts) and the downloaded-font list. */
function renderFontControls() {
  const options = [...BUILTIN_FONTS.map(f => ({ id: f.id, name: f.name })), ...downloadedFonts.map(f => ({ id: `g:${f.slug}`, name: `${f.family}（已下載）` }))];
  /**
   * Fill one font menu and select the remembered choice.
   * @param {HTMLSelectElement} sel Menu
   * @param {string} key "fontBody" or "fontHead"
   * @param {string} fallback Default choice id
   * @param {Array<{id: string, name: string}>} extra Options shown first (e.g. 跟著介面風格)
   */
  const fill = (sel, key, fallback, extra) => {
    const current = fontChoice(key, fallback).id;
    sel.innerHTML = [...extra, ...options].map(o => `<option value="${escHtml(o.id)}"${o.id === current ? ' selected' : ''}>${escHtml(o.name)}</option>`).join('');
  };
  fill($('#fontBody'), 'fontBody', 'noto-sans', []);
  fill($('#fontHead'), 'fontHead', 'auto', [{ id: 'auto', name: '跟著介面風格' }]);
  $('#fontList').innerHTML = downloadedFonts.map(f => `<li><span><span class="font-name" style='font-family:${fontStack({ id: `g:${f.slug}`, family: f.family }).replace(/'/g, '')}'>${escHtml(f.family)}</span>
    <span class="small muted">　${f.files} 個檔案・${(f.bytes / 1048576).toFixed(1)} MB</span></span><button class="btn btn-ghost btn-sm" data-font-del="${escHtml(f.slug)}">刪除</button></li>`).join('');
  downloadedFonts.forEach(f => ensureFontCss({ id: `g:${f.slug}` }));
}

/**
 * Remember a font choice from one of the menus and apply it.
 * @param {string} key "fontBody" or "fontHead"
 * @param {string} id Chosen option id
 */
function chooseFont(key, id) {
  const font = downloadedFonts.find(f => `g:${f.slug}` === id);
  save(key, JSON.stringify(font ? { id, family: font.family } : { id }));
  applyFontChoices();
}

/** Load the list of downloaded fonts from this computer. */
async function loadFonts() {
  try {
    const res = await fetch('/api/fonts');
    downloadedFonts = res.ok ? (await res.json()).fonts || [] : [];
  } catch (e) {
    downloadedFonts = [];
  }
  renderFontControls();
}

/** Download the Google Fonts family typed in the box. */
async function downloadGoogleFont() {
  const family = $('#gfName').value.trim();
  if (!family) { showToast('請輸入 Google Fonts 上的字型名稱', 'warning'); return; }
  const btn = $('#gfGet');
  btn.disabled = true; btn.textContent = '下載中…';
  showToast(`正在下載 ${family}，中文字型可能要一分鐘…`, 'info', 6000);
  try {
    const res = await fetch('/api/fonts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ family }) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    $('#gfName').value = '';
    await loadFonts();
    showToast(`已下載 ${data.family}，可以在上面的選單選用`, 'success');
  } catch (e) {
    showToast(e.message, 'error', 8000);
  } finally {
    btn.disabled = false; btn.textContent = '下載';
  }
}

/**
 * Delete a downloaded font after confirmation; a page using it goes back to the default.
 * @param {string} slug Font folder name
 */
async function deleteFont(slug) {
  const font = downloadedFonts.find(f => f.slug === slug);
  if (!(await askConfirm(`刪除已下載的字型 ${font ? font.family : slug}？`, { okLabel: '刪除', danger: true }))) return;
  await fetch(`/api/fonts/${encodeURIComponent(slug)}`, { method: 'DELETE' });
  ['fontBody', 'fontHead'].forEach(key => { if (fontChoice(key, '').id === `g:${slug}`) forget(key); });
  await loadFonts();
  applyFontChoices();
}

$('#fontBody').addEventListener('change', e => chooseFont('fontBody', e.target.value));
$('#fontHead').addEventListener('change', e => chooseFont('fontHead', e.target.value));
$('#gfGet').addEventListener('click', downloadGoogleFont);
$('#gfName').addEventListener('keydown', e => { if (e.key === 'Enter') downloadGoogleFont(); });
$('#fontList').addEventListener('click', e => { const b = e.target.closest('[data-font-del]'); if (b) deleteFont(b.dataset.fontDel); });

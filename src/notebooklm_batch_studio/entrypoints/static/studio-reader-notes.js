/* Gemini Notebook 學習工作室 — PDF reader annotations, bookmarks, resume position,
   collapsible margin comments, and horizontal splitter. */

let readerCurrentPage = 1;
let kpViewMode = 'page';

/**
 * Build the localStorage key for per-lecture reader state.
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @returns {string} Storage key
 */
function readerStateKey(code, no) {
  return `nbs.reader.${code}.${no}`;
}

/**
 * Load saved reader state (lastPage, bookmarks, userHighlights, commentsCollapsed, splitPct).
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @returns {object} Saved state with safe defaults
 */
function loadReaderLocal(code, no) {
  const def = { lastPage: 1, bookmarks: [], userHighlights: [], commentsCollapsed: false, splitPct: 28 };
  try {
    const raw = localStorage.getItem(readerStateKey(code, no));
    return raw ? { ...def, ...JSON.parse(raw) } : def;
  } catch (e) {
    return def;
  }
}

/**
 * Persist partial updates to per-lecture reader state in localStorage.
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @param {object} patch Fields to merge
 * @returns {object} Updated state
 */
function saveReaderLocal(code, no, patch) {
  const next = { ...loadReaderLocal(code, no), ...patch };
  try {
    localStorage.setItem(readerStateKey(code, no), JSON.stringify(next));
  } catch (e) {}
  return next;
}

/**
 * Update tracked current page, persist lastPage, and refresh resume button + active margin comments.
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @param {number} pageNum Currently visible page number
 * @returns {void}
 */
function updateReaderPageTracking(code, no, pageNum) {
  readerCurrentPage = pageNum;
  saveReaderLocal(code, no, { lastPage: pageNum });
  const btn = document.getElementById('readerResumeBtn');
  if (btn) btn.textContent = `📍 續讀 p.${pageNum}`;
  syncActivePageComments(pageNum);
}

/**
 * Jump smoothly to a specific PDF page number.
 * @param {number} pageNum Target page number
 * @returns {void}
 */
function jumpToReaderPage(pageNum) {
  const el = document.getElementById(`readerPage-${pageNum}`);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Jump to the last saved reading page for the active lecture.
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @returns {void}
 */
function jumpToLastReadPage(code, no) {
  const st = loadReaderLocal(code, no);
  jumpToReaderPage(st.lastPage || 1);
}

/**
 * Toggle a bookmark on the current PDF page and re-render bookmark pills.
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @returns {void}
 */
function toggleReaderBookmark(code, no) {
  const st = loadReaderLocal(code, no);
  const exists = st.bookmarks.some(b => b.page === readerCurrentPage);
  const bookmarks = exists
    ? st.bookmarks.filter(b => b.page !== readerCurrentPage)
    : [...st.bookmarks, { page: readerCurrentPage, label: `p.${readerCurrentPage}` }].sort((a, b) => a.page - b.page);
  saveReaderLocal(code, no, { bookmarks });
  renderReaderBookmarks(code, no);
  if (typeof showToast === 'function') showToast(exists ? `已移除 p.${readerCurrentPage} 書籤` : `已加入 p.${readerCurrentPage} 書籤`, 'info', 1800);
}

/**
 * Render clickable bookmark pills in #readerBookmarksBar.
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @returns {void}
 */
function renderReaderBookmarks(code, no) {
  const { bookmarks } = loadReaderLocal(code, no);
  const count = document.getElementById('bmCount');
  const pop = document.getElementById('bmPop');
  if (count) count.textContent = String(bookmarks.length);
  if (!pop) return;
  if (!bookmarks.length) {
    pop.innerHTML = '<div class="small muted" style="padding:8px 10px">尚無書籤，點左側「加書籤」加入目前頁碼</div>';
    return;
  }
  pop.innerHTML = bookmarks.map(b =>
    `<div class="bm-pop-row"><button type="button" class="bm-pop-go" onclick="jumpToReaderPage(${b.page});document.getElementById('bmPick')?.classList.remove('open')">🔖 ${escHtml(b.label)}</button>` +
    `<button type="button" class="bm-del" aria-label="移除書籤" onclick="removeReaderBookmark('${escHtml(code)}',${no},${b.page})">×</button></div>`
  ).join('');
}

/**
 * Toggle the bookmark dropdown menu open/closed.
 * @param {MouseEvent} e Click event
 * @returns {void}
 */
function toggleBmMenu(e) {
  e.stopPropagation();
  const wrap = document.getElementById('bmPick');
  if (!wrap) return;
  const open = wrap.classList.toggle('open');
  document.getElementById('bmMenuBtn')?.setAttribute('aria-expanded', String(open));
}

document.addEventListener('click', e => {
  const wrap = document.getElementById('bmPick');
  if (wrap && !wrap.contains(e.target)) {
    wrap.classList.remove('open');
    document.getElementById('bmMenuBtn')?.setAttribute('aria-expanded', 'false');
  }
});

/**
 * Remove a saved bookmark by page number.
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @param {number} page Page number to remove
 * @returns {void}
 */
function removeReaderBookmark(code, no, page) {
  const st = loadReaderLocal(code, no);
  saveReaderLocal(code, no, { bookmarks: st.bookmarks.filter(b => b.page !== page) });
  renderReaderBookmarks(code, no);
}

/**
 * Toggle collapse/expand state of the margin comments column.
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @returns {void}
 */
function toggleReaderComments(code, no) {
  const layout = document.querySelector('.reader-layout');
  const btn = document.getElementById('readerToggleCommentsBtn');
  if (!layout) return;
  const collapsed = layout.classList.toggle('kp-collapsed');
  saveReaderLocal(code, no, { commentsCollapsed: collapsed });
  if (btn) btn.textContent = collapsed ? '展開重點備註' : '收合重點';
}

/**
 * Mark margin comments belonging to the active page so comments follow PDF scrolling.
 * @param {number} pageNum Active page number
 * @returns {void}
 */
/**
 * Toggle margin comments between current-page-only (e-book margin style) and all pages.
 * @returns {void}
 */
function toggleKpViewMode() {
  kpViewMode = kpViewMode === 'page' ? 'all' : 'page';
  const btn = document.getElementById('kpModeBtn');
  if (btn) btn.textContent = kpViewMode === 'page' ? '顯示全部' : '僅看本頁';
  syncActivePageComments(readerCurrentPage);
}

/**
 * Show only margin comments anchored to the active PDF page (or all when toggled).
 * @param {number} pageNum Active page number
 * @returns {void}
 */
function syncActivePageComments(pageNum) {
  let shown = 0;
  document.querySelectorAll('#keyPointList .kp-item').forEach(item => {
    const pdfPage = Number(item.dataset.pdfPage || 0);
    const match = kpViewMode === 'all' || pdfPage === pageNum;
    item.hidden = !match;
    item.classList.toggle('is-on-page', pdfPage === pageNum);
    if (match) shown++;
  });
  const empty = document.getElementById('kpEmptyPage');
  if (empty) empty.hidden = kpViewMode === 'all' || shown > 0;
}

/**
 * Initialize horizontal drag resizing between the margin comments column and PDF pages.
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @returns {void}
 */
function initReaderSplitter(code, no) {
  const splitter = document.getElementById('readerSplitter');
  const layout = document.querySelector('.reader-layout');
  if (!splitter || !layout) return;
  const st = loadReaderLocal(code, no);
  layout.style.setProperty('--kp-col', `${st.splitPct || 28}%`);
  if (st.commentsCollapsed) {
    layout.classList.add('kp-collapsed');
    const btn = document.getElementById('readerToggleCommentsBtn');
    if (btn) btn.textContent = '展開重點備註';
  }
  splitter.addEventListener('pointerdown', e => {
    e.preventDefault();
    splitter.setPointerCapture(e.pointerId);
    const move = ev => {
      const r = layout.getBoundingClientRect();
      const pct = Math.max(18, Math.min(48, ((ev.clientX - r.left) / r.width) * 100));
      layout.style.setProperty('--kp-col', `${pct.toFixed(1)}%`);
      saveReaderLocal(code, no, { splitPct: Math.round(pct) });
    };
    /**
     * Clean up pointermove/pointerup listeners when splitter drag ends.
     * @returns {void}
     */
    const up = () => {
      splitter.removeEventListener('pointermove', move);
      splitter.removeEventListener('pointerup', up);
    };
    splitter.addEventListener('pointermove', move);
    splitter.addEventListener('pointerup', up);
  });
}

/**
 * Add a user highlight + comment from selected PDF text and refresh highlights + list.
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @param {number} page Page number
 * @param {string} quote Selected text
 * @returns {void}
 */
function saveUserPdfHighlight(code, no, page, quote) {
  const note = window.prompt('為這段文字加上備註（可留空）：', '');
  if (note === null) return;
  const st = loadReaderLocal(code, no);
  const item = { id: `u_${Date.now()}`, page, quote: quote.slice(0, 220), note: note.trim(), importance: 4 };
  saveReaderLocal(code, no, { userHighlights: [...st.userHighlights, item] });
  if (typeof renderKeyPointList === 'function') renderKeyPointList();
  if (typeof highlightPage === 'function') highlightPage(page);
  if (typeof showToast === 'function') showToast('已加入個人標記與備註', 'success', 1800);
}

/**
 * Delete a saved user highlight by id and refresh the reader.
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @param {string} id User highlight id
 * @returns {void}
 */
function deleteUserPdfHighlight(code, no, id) {
  const st = loadReaderLocal(code, no);
  saveReaderLocal(code, no, { userHighlights: st.userHighlights.filter(h => h.id !== id) });
  if (typeof renderKeyPointList === 'function') renderKeyPointList();
  document.querySelectorAll('.reader-page[data-rendered="1"]').forEach(el => {
    if (typeof highlightPage === 'function') highlightPage(Number(el.dataset.page));
  });
}

/**
 * Listen for text selection inside #readerPages to show a quick highlight + comment button.
 * @param {function(): {code: string, no: number}|null} getCtx Context getter
 * @returns {void}
 */
function hookPdfSelectionHighlight(getCtx) {
  const pages = document.getElementById('readerPages');
  if (!pages) return;
  pages.addEventListener('mouseup', () => {
    const sel = window.getSelection();
    const text = sel ? sel.toString().trim() : '';
    let pop = document.getElementById('readerSelPop');
    if (text.length < 3) { if (pop) pop.hidden = true; return; }
    const anchor = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement);
    const pageEl = anchor && anchor.closest('.reader-page');
    const ctx = getCtx();
    if (!pageEl || !ctx) return;
    if (!pop) {
      pop = document.createElement('button');
      pop.id = 'readerSelPop';
      pop.type = 'button';
      pop.className = 'reader-sel-pop';
      pop.textContent = '🖍️ 標記並加備註';
      document.body.appendChild(pop);
    }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    pop.style.left = `${Math.max(12, rect.left + rect.width / 2 - 64)}px`;
    pop.style.top = `${Math.max(12, rect.top - 38)}px`;
    pop.hidden = false;
    pop.onclick = () => {
      pop.hidden = true;
      sel.removeAllRanges();
      saveUserPdfHighlight(ctx.code, ctx.no, Number(pageEl.dataset.page || 1), text);
    };
  });
}

Object.assign(window, {
  loadReaderLocal,
  saveReaderLocal,
  updateReaderPageTracking,
  jumpToReaderPage,
  jumpToLastReadPage,
  toggleReaderBookmark,
  renderReaderBookmarks,
  removeReaderBookmark,
  toggleReaderComments,
  toggleKpViewMode,
  toggleBmMenu,
  syncActivePageComments,
  initReaderSplitter,
  deleteUserPdfHighlight,
  hookPdfSelectionHighlight,
});

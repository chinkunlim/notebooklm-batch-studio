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
  if (btn) btn.textContent = `續讀 p.${pageNum}`;
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
    `<div class="bm-pop-row"><button type="button" class="bm-pop-go" onclick="jumpToReaderPage(${b.page});document.getElementById('bmPick')?.classList.remove('open')">${escHtml(b.label)}</button>` +
    `<button type="button" class="bm-del" aria-label="移除書籤" onclick="removeReaderBookmark(event,'${escHtml(code)}',${no},${b.page})">×</button></div>`
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
 * Remove a saved bookmark by page number without closing the bookmark dropdown.
 * @param {MouseEvent} e Click event
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @param {number} page Page number to remove
 * @returns {void}
 */
function removeReaderBookmark(e, code, no, page) {
  if (e) e.stopPropagation();
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
  if (btn) btn.innerHTML = kpViewMode === 'page' ? '<span>顯示</span><span>全部</span>' : '<span>僅看</span><span>本頁</span>';
  syncActivePageComments(readerCurrentPage);
}

/**
 * Position margin comments next to their highlighted line inside #readerPages (Word/e-book style).
 * @param {number} [pageNum] Active page number
 * @returns {void}
 */
function syncActivePageComments(pageNum) {
  const list = document.getElementById('keyPointList');
  const pages = document.getElementById('readerPages');
  if (!list || !pages) return;
  const listRect = list.getBoundingClientRect();
  const pagesRect = pages.getBoundingClientRect();
  let lastBottom = 36;
  let shown = 0;
  list.classList.toggle('kp-all-mode', kpViewMode === 'all');
  list.querySelectorAll('.kp-item').forEach(item => {
    if (kpViewMode === 'all') { item.hidden = false; item.style.position = ''; item.style.top = ''; shown++; return; }
    const anchor = document.querySelector(`.reader-page [data-kp-anchor="${item.dataset.kpIdx}"]`);
    if (!anchor) { item.hidden = true; return; }
    const ar = anchor.getBoundingClientRect();
    if (ar.bottom < pagesRect.top - 40 || ar.top > pagesRect.bottom + 40) { item.hidden = true; return; }
    item.hidden = false;
    const rawTop = Math.max(lastBottom, ar.top - listRect.top);
    item.style.position = 'absolute';
    item.style.top = `${Math.round(rawTop)}px`;
    item.style.left = '0';
    item.style.right = '0';
    lastBottom = rawTop + (item.offsetHeight || 72) + 8;
    shown++;
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
 * Toggle inverted night-reading mode on the PDF canvas and persist the preference.
 * @returns {void}
 */
function toggleReaderNightMode() {
  const pages = document.getElementById('readerPages');
  const btn = document.getElementById('readerNightBtn');
  if (!pages) return;
  const on = pages.classList.toggle('night-mode');
  if (btn) btn.classList.toggle('on', on);
  try { localStorage.setItem('v05.readerNight', on ? '1' : '0'); } catch (e) { /* ignore */ }
}

/**
 * Toggle showing only PDF pages that have highlights, bookmarks, or Q&A citations.
 * @returns {void}
 */
function toggleReaderFilterImportant() {
  const btn = document.getElementById('readerFilterBtn');
  const pages = [...document.querySelectorAll('#readerPages .reader-page')];
  if (!pages.length) return;
  const active = btn ? btn.classList.toggle('on') : false;
  if (!active) {
    pages.forEach(p => p.classList.remove('is-filtered-out'));
    return;
  }
  const st = typeof currentStudyCourse !== 'undefined' && currentStudyCourse
    ? loadReaderLocal(currentStudyCourse.code, activeStudyLectureNo) : { bookmarks: [] };
  const bmSet = new Set(st.bookmarks || []);
  let shown = 0;
  pages.forEach(p => {
    const pgNo = Number(p.dataset.page || 0);
    const hasHit = bmSet.has(pgNo) || !!p.querySelector('.kp-hl');
    p.classList.toggle('is-filtered-out', !hasHit);
    if (hasHit) shown += 1;
  });
  if (!shown) {
    pages.forEach(p => p.classList.remove('is-filtered-out'));
    if (btn) btn.classList.remove('on');
    if (typeof showToast === 'function') showToast('目前已載入的頁面尚無標記或書籤', 'info', 2400);
  }
}

/**
 * Execute one quick action from the PDF text-selection popover.
 * @param {string} act Action name ('hl' | 'ask' | 'note')
 * @param {{code: string, no: number}} ctx Active course and lecture context
 * @param {number} pageNo 1-based page number
 * @param {string} text Selected PDF text
 * @returns {Promise<void>}
 */
async function runPdfSelectionAction(act, ctx, pageNo, text) {
  if (act === 'hl') {
    saveUserPdfHighlight(ctx.code, ctx.no, pageNo, text);
  } else if (act === 'ask') {
    if (typeof toggleQaDrawer === 'function') toggleQaDrawer(true);
    const inp = document.getElementById('qaQuestionInput');
    if (inp) { inp.value = `請用白話與重點解釋講義這段：\n「${text.slice(0, 400)}」`; inp.focus(); }
  } else if (act === 'note' && typeof persistQaNote === 'function') {
    await persistQaNote({
      title: `講義摘錄 p.${pageNo}`,
      content_markdown: `> ${text}`,
      lecture_no: ctx.no,
      tags: ['講義摘錄'],
      source_scene: 'pdf_selection',
    });
  }
}

/**
 * Listen for text selection inside #readerPages to show quick actions (highlight, ask AI, save note).
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
      pop = document.createElement('div');
      pop.id = 'readerSelPop';
      pop.className = 'reader-sel-pop';
      pop.innerHTML = '<button type="button" data-act="hl">️ 標記</button><button type="button" data-act="ask">問這段</button><button type="button" data-act="note">存筆記</button>';
      document.body.appendChild(pop);
    }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    pop.style.left = `${Math.max(12, rect.left + rect.width / 2 - 110)}px`;
    pop.style.top = `${Math.max(12, rect.top - 40)}px`;
    pop.hidden = false;
    pop.onclick = async e => {
      const act = e.target.closest('button')?.dataset?.act;
      if (!act) return;
      pop.hidden = true;
      sel.removeAllRanges();
      await runPdfSelectionAction(act, ctx, Number(pageEl.dataset.page || 1), text);
    };
  });
}

/**
 * Register Q&A citation snippets so rendered lecture PDF pages highlight them in the citation color.
 * @param {Array<{cited_text?: string}>} refs Reference items from Q&A response
 * @returns {void}
 */
function registerQaCitations(refs) {
  if (!Array.isArray(refs) || !refs.length) return;
  const list = Array.isArray(window._qaCitationHighlights) ? window._qaCitationHighlights : [];
  refs.forEach((r, idx) => {
    const raw = String(r?.cited_text || '').replace(/^\[\d+\]\s*/, '').trim();
    if (raw.length < 6) return;
    if (list.some(x => x.quote === raw)) return;
    const pgMatch = raw.match(/(?:p\.?|page|第)\s*(\d+)/i);
    list.push({ id: `qa-${Date.now()}-${idx}`, quote: raw, page: pgMatch ? Number(pgMatch[1]) : 0, importance: 5 });
  });
  window._qaCitationHighlights = list;
  document.querySelectorAll('.reader-page[data-rendered="1"]').forEach(el => {
    if (typeof highlightPage === 'function') highlightPage(Number(el.dataset.page));
  });
}

/**
 * Find a Q&A citation snippet inside the open lecture PDF, jump to its page, and highlight it.
 * @param {string} citedText Cited passage from Q&A reference
 * @returns {Promise<void>}
 */
async function highlightQaCitationInPdf(citedText) {
  const raw = String(citedText || '').replace(/^\[\d+\]\s*/, '').trim();
  if (!raw) return;
  if (typeof selectBenchItem === 'function') selectBenchItem('lecture');
  registerQaCitations([{ cited_text: raw }]);
  const doc = typeof window.getReaderDoc === 'function' ? window.getReaderDoc() : null;
  const normFn = typeof window.normPdfText === 'function' ? window.normPdfText : s => String(s).toLowerCase().trim();
  const needle = normFn(raw).slice(0, 26);
  const pgHint = raw.match(/(?:p\.?|page|第)\s*(\d+)/i);
  let targetPage = pgHint ? Number(pgHint[1]) : 0;
  if (doc && needle.length >= 6) {
    const total = doc.numPages || 0;
    const order = [];
    if (targetPage >= 1 && targetPage <= total) order.push(targetPage);
    for (let p = 1; p <= total; p += 1) if (p !== targetPage) order.push(p);
    for (const n of order) {
      const pg = await doc.getPage(n);
      const tc = await pg.getTextContent();
      const txt = normFn(tc.items.map(it => it.str).join(' ')).replace(/-\s+/g, '');
      if (txt.includes(needle)) { targetPage = n; break; }
    }
  }
  const entry = (window._qaCitationHighlights || []).find(x => x.quote === raw);
  if (entry && targetPage) { entry.page = targetPage; entry.foundOn = targetPage; }
  if (targetPage && typeof jumpToReaderPage === 'function') {
    jumpToReaderPage(targetPage);
    setTimeout(() => {
      if (typeof highlightPage === 'function') highlightPage(targetPage);
      const pageEl = document.getElementById(`readerPage-${targetPage}`);
      const hits = pageEl ? pageEl.querySelectorAll('.kp-hl.kp-i5') : [];
      if (hits.length) {
        hits[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
        hits.forEach(el => { el.classList.remove('kp-flash'); void el.offsetWidth; el.classList.add('kp-flash'); });
      }
    }, 260);
    return;
  }
  if (typeof showToast === 'function') showToast(`引用內容：${raw.slice(0, 140)}`, 'info', 4000);
}

Object.assign(window, {
  loadReaderLocal,
  saveReaderLocal,
  updateReaderPageTracking,
  jumpToReaderPage,
  jumpToPdfPage: jumpToReaderPage,
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
  registerQaCitations,
  highlightQaCitationInPdf,
  toggleReaderNightMode,
  toggleReaderFilterImportant,
});

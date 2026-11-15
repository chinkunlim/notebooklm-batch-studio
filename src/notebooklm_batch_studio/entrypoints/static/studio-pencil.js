/**
 * Gemini Notebook 學習工作室 — Apple Pencil & touch freehand annotation overlay for PDF pages.
 * Automatically captures Apple Pencil (`pointerType === 'pen'`) strokes on `.reader-page` while
 * preserving finger scrolling/pinch-zoom, and supports optional toggleable touch/mouse ink mode.
 */

const _pencilState = {
  mode: 'off', // 'off' | 'highlighter' | 'pen'
  color: '#3f8f6b',
  course: '',
  lecture: 0,
};

/**
 * Build localStorage key for freehand strokes on a specific lecture page.
 * @param {string} code Course code
 * @param {number} lecNo Lecture number
 * @param {number} pageNo 1-based page number
 * @returns {string} Storage key
 */
function _pencilStorageKey(code, lecNo, pageNo) {
  return `v05.pencil.${code}.${lecNo}.${pageNo}`;
}

/**
 * Load saved strokes array for a given page.
 * @param {string} code Course code
 * @param {number} lecNo Lecture number
 * @param {number} pageNo 1-based page number
 * @returns {Array<{d: string, color: string, width: number, opacity: number}>} Stroke list
 */
function _loadPageStrokes(code, lecNo, pageNo) {
  try {
    return JSON.parse(localStorage.getItem(_pencilStorageKey(code, lecNo, pageNo)) || '[]');
  } catch {
    return [];
  }
}

/**
 * Save strokes array for a given page.
 * @param {string} code Course code
 * @param {number} lecNo Lecture number
 * @param {number} pageNo 1-based page number
 * @param {Array<object>} strokes Stroke list
 */
function _savePageStrokes(code, lecNo, pageNo, strokes) {
  try {
    localStorage.setItem(_pencilStorageKey(code, lecNo, pageNo), JSON.stringify(strokes));
  } catch {
    // Ignore storage quota errors in private browsing.
  }
}

/**
 * Cycle freehand ink mode ('off' -> 'highlighter' -> 'pen' -> 'off') for finger/mouse users.
 * Note: Apple Pencil (`pointerType === 'pen'`) always draws even when mode is 'off'.
 * @returns {void}
 */
function toggleReaderPencilMode() {
  const order = ['off', 'highlighter', 'pen'];
  const next = order[(order.indexOf(_pencilState.mode) + 1) % order.length];
  _pencilState.mode = next;
  const btn = document.getElementById('readerPencilBtn');
  if (btn) {
    btn.classList.toggle('on', next !== 'off');
    btn.textContent = next === 'highlighter' ? '螢光筆中' : next === 'pen' ? '細筆批註中' : '手寫畫筆';
  }
  document.querySelectorAll('.pencil-layer').forEach(svg => {
    svg.classList.toggle('draw-all', next !== 'off');
  });
  const msg = next === 'off'
    ? '已切回閱讀捲動（iPad 使用 Apple Pencil 仍可直接落筆書寫）'
    : `已開啟${next === 'highlighter' ? '螢光筆' : '細字筆'}模式，可直接書寫劃記`;
  showToast(msg, 'info', 2200);
}

/**
 * Clear all freehand strokes on the currently visible PDF page.
 * @returns {void}
 */
function clearVisiblePagePencil() {
  if (!_pencilState.course) return;
  const pageNum = typeof currentVisiblePdfPage === 'function' ? currentVisiblePdfPage() : 1;
  localStorage.removeItem(_pencilStorageKey(_pencilState.course, _pencilState.lecture, pageNum));
  const svg = document.querySelector(`#readerPage-${pageNum} .pencil-layer`);
  if (svg) svg.innerHTML = '';
  showToast(`已清除第 ${pageNum} 頁手寫筆跡`, 'info', 1800);
}

/**
 * Mount SVG ink layers onto all `.reader-page` elements and hook Apple Pencil + touch events.
 * @param {string} code Course code
 * @param {number} lecNo Lecture number
 * @returns {void}
 */
function initReaderPencilLayers(code, lecNo) {
  _pencilState.course = code;
  _pencilState.lecture = lecNo;
  document.querySelectorAll('.reader-page').forEach(pageEl => {
    if (pageEl.querySelector('.pencil-layer')) return;
    const pageNo = Number(pageEl.dataset.page || 1);
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'pencil-layer' + (_pencilState.mode !== 'off' ? ' draw-all' : ''));
    svg.setAttribute('viewBox', '0 0 1000 1000');
    svg.setAttribute('preserveAspectRatio', 'none');
    _renderSavedStrokes(svg, code, lecNo, pageNo);
    _hookPencilEvents(pageEl, svg, { code, lecNo, pageNo });
    pageEl.appendChild(svg);
  });
}

/**
 * Render previously saved strokes into a page's SVG overlay.
 * @param {SVGSVGElement} svg Target SVG overlay
 * @param {string} code Course code
 * @param {number} lecNo Lecture number
 * @param {number} pageNo 1-based page number
 */
function _renderSavedStrokes(svg, code, lecNo, pageNo) {
  const strokes = _loadPageStrokes(code, lecNo, pageNo);
  svg.innerHTML = strokes.map(s =>
    `<path d="${escAttr(s.d)}" fill="none" stroke="${escAttr(s.color)}" stroke-width="${s.width}" stroke-opacity="${s.opacity}" stroke-linecap="round" stroke-linejoin="round"/>`
  ).join('');
}

/**
 * Map a pointer event inside a PDF page to normalized 0..1000 SVG coordinates.
 * @param {HTMLElement} pageEl PDF page container
 * @param {PointerEvent} e Pointer event
 * @returns {[number, number]} Normalized `[x, y]`
 */
function _toSvgPoint(pageEl, e) {
  const r = pageEl.getBoundingClientRect();
  const x = Math.max(0, Math.min(1000, ((e.clientX - r.left) / Math.max(1, r.width)) * 1000));
  const y = Math.max(0, Math.min(1000, ((e.clientY - r.top) / Math.max(1, r.height)) * 1000));
  return [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
}

/**
 * Start a new SVG stroke element from a pointerdown event.
 * @param {HTMLElement} pageEl PDF page container
 * @param {SVGSVGElement} svg Overlay SVG element
 * @param {PointerEvent} e Pointer down event
 * @returns {object} Active stroke descriptor
 */
function _beginPencilStroke(pageEl, svg, e) {
  const isHighlighter = _pencilState.mode === 'highlighter' || (e.pointerType === 'pen' && _pencilState.mode === 'off');
  const pressure = typeof e.pressure === 'number' && e.pressure > 0 ? e.pressure : 0.5;
  const width = isHighlighter ? Math.round((16 + pressure * 10) * 10) / 10 : Math.round((2.5 + pressure * 2.5) * 10) / 10;
  const opacity = isHighlighter ? 0.34 : 0.9;
  const color = getComputedStyle(document.documentElement).getPropertyValue('--hl-4').trim() || _pencilState.color;
  const [x, y] = _toSvgPoint(pageEl, e);
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  const d = `M ${x} ${y}`;
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', color);
  path.setAttribute('stroke-width', String(width));
  path.setAttribute('stroke-opacity', String(opacity));
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');
  path.setAttribute('d', d);
  svg.appendChild(path);
  try { pageEl.setPointerCapture(e.pointerId); } catch {}
  return { pointerId: e.pointerId, d, color, width, opacity, path };
}

/**
 * Attach pointer handlers that prioritize Apple Pencil (`pointerType === 'pen'`) and optional draw mode.
 * @param {HTMLElement} pageEl PDF page container
 * @param {SVGSVGElement} svg Overlay SVG element
 * @param {{code: string, lecNo: number, pageNo: number}} ctx Page storage context
 */
function _hookPencilEvents(pageEl, svg, ctx) {
  let active = null;
  pageEl.addEventListener('pointerdown', e => {
    if ((e.pointerType !== 'pen' && _pencilState.mode === 'off') || (e.button && e.button !== 0)) return;
    e.preventDefault();
    active = _beginPencilStroke(pageEl, svg, e);
  });
  pageEl.addEventListener('pointermove', e => {
    if (!active || e.pointerId !== active.pointerId) return;
    e.preventDefault();
    const [x, y] = _toSvgPoint(pageEl, e);
    active.d += ` L ${x} ${y}`;
    active.path.setAttribute('d', active.d);
  });
  const finish = e => {
    if (!active || e.pointerId !== active.pointerId) return;
    const list = _loadPageStrokes(ctx.code, ctx.lecNo, ctx.pageNo);
    list.push({ d: active.d, color: active.color, width: active.width, opacity: active.opacity });
    _savePageStrokes(ctx.code, ctx.lecNo, ctx.pageNo, list);
    active = null;
  };
  pageEl.addEventListener('pointerup', finish);
  pageEl.addEventListener('pointercancel', finish);
}

/**
 * Enable two-finger pinch-to-zoom inside the PDF reader without zooming the whole browser page.
 * @param {HTMLElement | null} pagesEl Scrollable PDF pages container
 * @param {Function} getScale Callback returning current zoom scale
 * @param {Function} applyZoom Callback accepting scale delta
 */
function hookReaderPinchZoom(pagesEl, getScale, applyZoom) {
  if (!pagesEl || pagesEl.dataset.pinchHooked) return;
  pagesEl.dataset.pinchHooked = '1';
  let d0 = 0, ratio = 1;
  const dist = t => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
  ['gesturestart', 'gesturechange', 'gestureend'].forEach(ev => pagesEl.addEventListener(ev, e => e.preventDefault(), { passive: false }));
  pagesEl.addEventListener('touchstart', e => { if (e.touches.length === 2) { d0 = dist(e.touches); ratio = 1; } }, { passive: true });
  pagesEl.addEventListener('touchmove', e => {
    if (e.touches.length !== 2 || !d0) return;
    e.preventDefault();
    ratio = Math.min(2.2, Math.max(0.6, dist(e.touches) / d0));
    pagesEl.style.transformOrigin = 'center top';
    pagesEl.style.transform = `scale(${ratio})`;
  }, { passive: false });
  /** Finalize pinch gesture and apply zoom delta. */
  const endPinch = () => {
    if (!d0) return;
    pagesEl.style.transform = '';
    const scale = getScale();
    const delta = Math.round(scale * ratio * 20) / 20 - scale;
    d0 = 0; ratio = 1; if (Math.abs(delta) >= 0.05) applyZoom(delta);
  };
  pagesEl.addEventListener('touchend', endPinch, { passive: true });
  pagesEl.addEventListener('touchcancel', endPinch, { passive: true });
}

/**
 * Inspect current text selection inside `#readerPages` and position the floating action popover.
 * @param {Function} getCtx Callback returning `{ code, no }`
 */
function _checkPdfTextSelection(getCtx) {
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
    pop.innerHTML = '<button type="button" data-act="hl">標記</button><button type="button" data-act="ask">問這段</button><button type="button" data-act="note">存筆記</button>';
    document.body.appendChild(pop);
  }
  const rect = sel.getRangeAt(0).getBoundingClientRect();
  const maxLeft = Math.max(12, window.innerWidth - 230);
  pop.style.left = `${Math.min(maxLeft, Math.max(12, rect.left + rect.width / 2 - 110))}px`;
  pop.style.top = `${Math.max(12, rect.top - 44)}px`;
  pop.hidden = false;
  pop.onclick = async e => {
    const act = e.target.closest('button')?.dataset?.act;
    if (!act) return;
    pop.hidden = true;
    sel.removeAllRanges();
    await runPdfSelectionAction(act, ctx, Number(pageEl.dataset.page || 1), text);
  };
}

/**
 * Bind pointer, touch, and selectionchange listeners on `#readerPages` for PDF text actions.
 * @param {Function} getCtx Callback returning `{ code, no }`
 */
function hookPdfSelectionHighlight(getCtx) {
  const pages = document.getElementById('readerPages');
  if (!pages) return;
  let selTimer = null;
  pages.addEventListener('pointerup', () => setTimeout(() => _checkPdfTextSelection(getCtx), 40));
  pages.addEventListener('touchend', () => setTimeout(() => _checkPdfTextSelection(getCtx), 120));
  document.addEventListener('selectionchange', () => {
    clearTimeout(selTimer);
    selTimer = setTimeout(() => _checkPdfTextSelection(getCtx), 220);
  });
}

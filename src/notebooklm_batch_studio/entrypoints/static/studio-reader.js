/* Gemini Notebook 學習工作室 — course material reader (ES module).
   Shows the lecture's own PDF with pdf.js (pages render when scrolled into view) and highlights the
   key points Gemini Notebook picked: each point carries a verbatim quote and page, found in the page's
   text layer and marked in one of three colours by importance. Uses globals from studio-app.js / studio.js:
   currentStudyCourse, activeStudyLectureNo, escHtml, showToast, askConfirm. */

import * as pdfjsLib from '/static/vendor/pdfjs/pdf.min.mjs';

pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.mjs';

/** State of the open document; replaced each time a lecture is opened. */
let reader = { doc: null, scale: 1.25, points: [], observer: null, pageObserver: null, token: 0, autoTried: new Set() };

/**
 * Lower-case, drop punctuation and collapse whitespace, so a quote is found regardless of line breaks,
 * a missing full stop or curly quotes. Hyphens stay (a line-end hyphen is handled when joining lines).
 * @param {string} text Text to normalise
 * @returns {string} Normalised text
 */
function norm(text) {
  return String(text).toLowerCase().replace(/[.,;:!?"'“”‘’()（）「」『』，。；：！？、]/g, ' ').replace(/\s+/g, ' ').trim();
}

/**
 * Stop observing pages of the previous document (called when leaving the tab).
 */
function stopReader() {
  if (reader.observer) reader.observer.disconnect();
  if (reader.pageObserver) reader.pageObserver.disconnect();
  reader.token += 1;
}

/**
 * Render the reader toolbar, bookmarks bar, and split layout inside #readerContainer.
 * @param {HTMLElement} box Container element
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @param {string} pdfUrl Source PDF URL
 */
function renderReaderShell(box, code, no, pdfUrl) {
  const st = typeof loadReaderLocal === 'function' ? loadReaderLocal(code, no) : { lastPage: 1 };
  box.innerHTML = `
    <div class="reader-bar">
      <div class="reader-tools">
        <button class="icon-btn" onclick="readerZoom(-0.15)" aria-label="縮小"><i class="icon-zoom-out"></i></button>
        <button type="button" class="reader-zoom-pill" id="readerZoomLabel" onclick="cycleReaderZoom()" title="點擊切換 小(125%) / 中 / 大(200%)">${Math.round(reader.scale * 100)}%</button>
        <button class="icon-btn" onclick="readerZoom(0.15)" aria-label="放大"><i class="icon-zoom-in"></i></button>
        <a class="btn btn-ghost btn-sm" href="${pdfUrl}" target="_blank" rel="noopener">新分頁開啟</a>
        <button type="button" class="btn btn-ghost btn-sm" id="readerResumeBtn" onclick="jumpToLastReadPage('${escHtml(code)}',${no})">📍 續讀 p.${st.lastPage || 1}</button>
        <button type="button" class="btn btn-ghost btn-sm" onclick="toggleReaderBookmark('${escHtml(code)}',${no})">🔖 書籤</button>
        <button type="button" class="btn btn-ghost btn-sm" id="readerToggleCommentsBtn" onclick="toggleReaderComments('${escHtml(code)}',${no})">收合重點</button>
      </div>
      <div class="reader-legend">
        <span class="kp-dot kp-i3"></span>必考核心 <span class="kp-dot kp-i2"></span>重要概念 <span class="kp-dot kp-i1"></span>補充 <span class="kp-dot kp-i4"></span>個人標記
      </div>
    </div>
    <div id="readerBookmarksBar" class="reader-bookmarks-bar" hidden></div>
    <div class="reader-layout">
      <aside id="keyPointList" class="kp-list">讀取重點中…</aside>
      <div id="readerSplitter" class="reader-splitter" role="separator" aria-orientation="vertical" title="拖曳調整重點欄與 PDF 寬度"></div>
      <div id="readerPages" class="reader-pages">讀取課件中…</div>
    </div>`;
  if (typeof initReaderSplitter === 'function') initReaderSplitter(code, no);
  if (typeof renderReaderBookmarks === 'function') renderReaderBookmarks(code, no);
  if (typeof hookPdfSelectionHighlight === 'function') hookPdfSelectionHighlight(() => ({ code, no }));
}

/**
 * Open the reader for the selected lecture: PDF pages plus the key-point list.
 * @returns {Promise<void>}
 */
async function loadReader() {
  const box = document.getElementById('readerContainer');
  if (!currentStudyCourse) return;
  if (activeStudyLectureNo === null) {
    box.innerHTML = '<div class="empty-state">講義是一講一份：請先在「課程目錄」選一講。</div>';
    return;
  }
  stopReader();
  const token = reader.token;
  const code = currentStudyCourse.code;
  const no = activeStudyLectureNo;
  const pdfUrl = `/api/courses/${encodeURIComponent(code)}/lectures/${no}/source.pdf`;
  renderReaderShell(box, code, no, pdfUrl);
  loadKeyPoints(code, no);
  try {
    const doc = await pdfjsLib.getDocument(pdfUrl).promise;
    if (token !== reader.token) return;
    reader.doc = doc;
    await layoutPages(token);
  } catch (e) {
    document.getElementById('readerPages').innerHTML =
      `<div class="empty-state">讀不到這一講的 PDF：${escHtml(e.message)}<br>（課程資料夾裡的檔案可能被移動或改名了）</div>`;
  }
}

/**
 * Load the saved key points and draw the side list (auto-generates in background when missing).
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @returns {Promise<void>}
 */
async function loadKeyPoints(code, no) {
  const list = document.getElementById('keyPointList');
  try {
    const res = await fetch(`/api/courses/${encodeURIComponent(code)}/lectures/${no}/key-points`);
    reader.points = res.ok ? (await res.json()).points || [] : [];
  } catch (e) {
    reader.points = [];
  }
  renderKeyPointList();
  const key = `${code}:${no}`;
  if (!reader.points.length && !reader.autoTried.has(key)) {
    reader.autoTried.add(key);
    generateKeyPoints(false, true);
  }
  if (!list) return;
}

/**
 * Draw the key-point list; each item jumps to its page.
 */
function renderKeyPointList() {
  const list = document.getElementById('keyPointList');
  if (!list || !currentStudyCourse) return;
  const code = currentStudyCourse.code;
  const no = activeStudyLectureNo;
  const userPts = typeof loadReaderLocal === 'function' ? loadReaderLocal(code, no).userHighlights : [];
  const allPts = [
    ...reader.points.map((p, i) => ({ ...p, _idx: i, _user: false })),
    ...userPts.map(u => ({ ...u, _user: true })),
  ].sort((a, b) => (a.page || 999) - (b.page || 999));
  if (!allPts.length) {
    list.innerHTML = `<div class="kp-empty">
        <p>正在自動整理講義重點，或可手動點擊下方按鈕：</p>
        <button class="btn btn-primary" onclick="generateKeyPoints(false)">產生重點</button></div>`;
    return;
  }
  list.innerHTML = `<div class="kp-head"><strong>重點與備註 ${allPts.length} 則</strong>
      <button class="link-btn" onclick="generateKeyPoints(true)">重新產生</button></div>` +
    allPts.map(p => {
      const click = p._user ? `jumpToReaderPage(${p.page || 1})` : `jumpToPoint(${p._idx})`;
      const idAttr = p._user ? '' : ` id="kpItem-${p._idx}"`;
      const del = p._user
        ? `<button type="button" class="kp-del" title="刪除個人標記" onclick="event.stopPropagation();deleteUserPdfHighlight('${escHtml(code)}',${no},'${escHtml(p.id)}')">✕</button>`
        : '';
      return `<div class="kp-item kp-i${p.importance || 2}"${idAttr} data-page="${p.page || 0}" onclick="${click}">
        <span class="kp-page">${p.page ? `p.${p.page}` : '—'}</span>
        <span class="kp-text"><span class="kp-quote">${escHtml(p.quote)}</span>
        ${p.note ? `<span class="kp-note">${escHtml(p.note)}</span>` : ''}</span>${del}</div>`;
    }).join('');
}

/**
 * Ask Gemini Notebook for the key points (asks the student first unless auto-triggered).
 * @param {boolean} force Ask again even when key points are saved
 * @param {boolean} [auto=false] True when auto-triggered on lecture open
 * @returns {Promise<void>}
 */
async function generateKeyPoints(force, auto = false) {
  if (!auto) {
    const ok = await askConfirm(force
      ? '重新請 Gemini Notebook 挑重點？舊的會被取代，並會用到一次對話額度。'
      : '請 Gemini Notebook 從這份講義挑出重點？會用到一次對話額度，結果會存起來重複使用。', { okLabel: '開始' });
    if (!ok) return;
  }
  const list = document.getElementById('keyPointList');
  list.innerHTML = '<div class="kp-empty">Gemini Notebook 正在閱讀講義、挑選重點（約 20–60 秒）…</div>';
  const code = currentStudyCourse.code;
  try {
    const res = await fetch(`/api/courses/${encodeURIComponent(code)}/lectures/${activeStudyLectureNo}/key-points`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ force }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    reader.points = data.points || [];
    renderKeyPointList();
    document.querySelectorAll('.reader-page[data-rendered="1"]').forEach(page => highlightPage(Number(page.dataset.page)));
    showToast(`找到 ${reader.points.length} 個重點`, 'success');
    if (typeof loadSideKeypoints === 'function') loadSideKeypoints();
  } catch (e) {
    showToast(`產生重點失敗：${e.message}`, 'error');
    renderKeyPointList();
  }
}

/**
 * Create one placeholder per page at the right size, then render pages as they scroll into view.
 * @param {number} token Document generation token (stale renders are dropped)
 * @returns {Promise<void>}
 */
async function layoutPages(token) {
  const pages = document.getElementById('readerPages');
  pages.innerHTML = '';
  const first = await reader.doc.getPage(1);
  const base = first.getViewport({ scale: 1 });
  const fitWidth = pages.clientWidth || 720;
  const width = Math.max(320, Math.round(fitWidth * Math.min(1.25, reader.scale / 2.0)));
  for (let n = 1; n <= reader.doc.numPages; n++) {
    const page = document.createElement('div');
    page.className = 'reader-page';
    page.id = `readerPage-${n}`;
    page.dataset.page = String(n);
    page.style.aspectRatio = `${base.width} / ${base.height}`;
    page.style.maxWidth = `${width}px`;
    page.innerHTML = `<span class="reader-page-no">${n} / ${reader.doc.numPages}</span>`;
    pages.appendChild(page);
  }
  reader.observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting && entry.target.dataset.rendered !== '1') renderPage(Number(entry.target.dataset.page), token);
    });
  }, { root: null, rootMargin: '600px 0px' });
  pages.querySelectorAll('.reader-page').forEach(el => reader.observer.observe(el));
  if (typeof updateReaderPageTracking === 'function' && currentStudyCourse) {
    const code = currentStudyCourse.code;
    const no = activeStudyLectureNo;
    reader.pageObserver = new IntersectionObserver(entries => {
      const vis = entries.filter(e => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio);
      if (vis.length) updateReaderPageTracking(code, no, Number(vis[0].target.dataset.page));
    }, { root: null, threshold: [0.35, 0.65] });
    pages.querySelectorAll('.reader-page').forEach(el => reader.pageObserver.observe(el));
  }
}

/**
 * Draw one page: canvas plus a selectable text layer, then highlight its key points.
 * @param {number} n Page number
 * @param {number} token Document generation token
 * @returns {Promise<void>}
 */
async function renderPage(n, token) {
  const holder = document.getElementById(`readerPage-${n}`);
  if (!holder || token !== reader.token) return;
  holder.dataset.rendered = '1';
  const page = await reader.doc.getPage(n);
  const cssWidth = holder.clientWidth || 800;
  const unscaled = page.getViewport({ scale: 1 });
  const viewport = page.getViewport({ scale: cssWidth / unscaled.width });
  const ratio = window.devicePixelRatio || 1;
  const canvas = document.createElement('canvas');
  canvas.width = Math.floor(viewport.width * ratio);
  canvas.height = Math.floor(viewport.height * ratio);
  canvas.style.width = '100%';
  const layer = document.createElement('div');
  layer.className = 'textLayer';
  layer.style.setProperty('--scale-factor', String(viewport.scale));
  layer.style.setProperty('--total-scale-factor', String(viewport.scale));
  holder.append(canvas, layer);
  await page.render({
    canvasContext: canvas.getContext('2d'), viewport,
    transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null,
  }).promise;
  const textLayer = new pdfjsLib.TextLayer({ textContentSource: page.streamTextContent(), container: layer, viewport });
  await textLayer.render();
  holder._textDivs = textLayer.textDivs;
  highlightPage(n);
}

/**
 * Join a page's text divs into searchable normalised text with span offsets.
 * @param {Array<HTMLElement>} divs TextLayer span elements
 * @returns {{text: string, starts: Array<number>, ends: Array<number>}} Joined text and span ranges
 */
function collectPageText(divs) {
  let text = '';
  const starts = [];
  const ends = [];
  divs.forEach(d => {
    let piece = norm(d.textContent);
    const hyphenated = /[a-z]-$/.test(piece);
    if (hyphenated) piece = piece.slice(0, -1);
    starts.push(text.length);
    text += piece;
    ends.push(text.length);
    if (!hyphenated && piece) text += ' ';
  });
  return { text, starts, ends };
}

/**
 * Mark the key points whose quote appears on this page (also tries points with a wrong or missing page,
 * because Gemini Notebook's page numbers can be off by one).
 * @param {number} n Page number
 */
function highlightPage(n) {
  const holder = document.getElementById(`readerPage-${n}`);
  const divs = holder && holder._textDivs;
  if (!divs || !divs.length) return;
  divs.forEach(d => d.classList.remove('kp-hl', 'kp-i1', 'kp-i2', 'kp-i3', 'kp-i4'));
  // Concatenate the page text and remember where each text piece starts and ends. A word hyphenated
  // at a line end ("mar-" + "riage") is joined, so quotes match the way Gemini Notebook writes them.
  const { text, starts, ends } = collectPageText(divs);
  const userPts = (typeof loadReaderLocal === 'function' && currentStudyCourse)
    ? loadReaderLocal(currentStudyCourse.code, activeStudyLectureNo).userHighlights : [];
  [...reader.points, ...userPts].forEach((p, i) => {
    if (p.page && Math.abs(p.page - n) > 1) return;
    const quote = norm(p.quote);
    let at = text.indexOf(quote);
    let len = quote.length;
    if (at < 0 && quote.length > 30) { at = text.indexOf(quote.slice(0, 30)); len = 30; }
    if (at < 0) return;
    divs.forEach((d, k) => {
      if (ends[k] > at && starts[k] < at + len) {
        d.classList.add('kp-hl', `kp-i${p.importance || 2}`);
        d.dataset.kp = String(i);
      }
    });
    if (i < reader.points.length) {
      p.foundOn = n;
      document.getElementById(`kpItem-${i}`)?.classList.add('found');
    }
  });
  markMissingPoints();
}

/**
 * Fade the key points whose quote was not found, but only once every page it could be on is drawn.
 */
function markMissingPoints() {
  const total = reader.doc ? reader.doc.numPages : 0;
  const drawn = n => !!document.getElementById(`readerPage-${n}`)?._textDivs;
  reader.points.forEach((p, i) => {
    if (p.foundOn) return;
    const pages = p.page ? [p.page - 1, p.page, p.page + 1].filter(n => n >= 1 && n <= total)
      : Array.from({ length: total }, (_, k) => k + 1);
    if (pages.length && pages.every(drawn)) document.getElementById(`kpItem-${i}`)?.classList.add('missing');
  });
}

/**
 * Scroll to a key point's page and flash its highlight.
 * @param {number} i Key point index
 */
function jumpToPoint(i) {
  const p = reader.points[i];
  const page = document.getElementById(`readerPage-${p.foundOn || p.page || 1}`);
  if (!page) return;
  page.scrollIntoView({ behavior: 'smooth', block: 'start' });
  setTimeout(() => {
    page.querySelectorAll(`[data-kp="${i}"]`).forEach(el => {
      el.classList.remove('kp-flash');
      void el.offsetWidth;  // restart the animation
      el.classList.add('kp-flash');
    });
  }, 450);
}

/**
 * Change the zoom level and lay the pages out again.
 * @param {number} delta Change in scale (e.g. 0.15)
 */
function readerZoom(delta) {
  reader.scale = Math.min(2.0, Math.max(1.25, Number((reader.scale + delta).toFixed(2))));
  document.getElementById('readerZoomLabel').textContent = `${Math.round(reader.scale * 100)}%`;
  if (!reader.doc) return;
  stopReader();
  layoutPages(reader.token);
}

/**
 * Cycle PDF zoom between Small (125%), Medium ((125+200)/2 = 163%), and Large (200%).
 * @returns {void}
 */
function cycleReaderZoom() {
  const minS = 1.25;
  const maxS = 2.0;
  const midS = Number(((minS + maxS) / 2).toFixed(2));
  const cur = reader.scale;
  reader.scale = cur < midS - 0.05 ? midS : (cur < maxS - 0.05 ? maxS : minS);
  document.getElementById('readerZoomLabel').textContent = `${Math.round(reader.scale * 100)}%`;
  if (!reader.doc) return;
  stopReader();
  layoutPages(reader.token);
}

Object.assign(window, {
  loadReader,
  stopReader,
  generateKeyPoints,
  jumpToPoint,
  readerZoom,
  cycleReaderZoom,
  renderKeyPointList,
  highlightPage,
});

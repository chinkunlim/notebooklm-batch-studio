/* Gemini Notebook 學習工作室 — the 研讀工作室 workbench and the study pages built around it: item tiles and their
   order / pins / arrangements, moving feature panels into the stage, the three layouts with draggable
   blocks, 本講重點, the overview's continue card, and today's review cards.
   Loaded after studio-player.js (uses the player and the shell helpers). */

/* ---------- Workbench: 講義 + 9 outputs, 4 arrangements ---------- */
/* The audio overview is always shown by the player itself, so it is not repeated as a tile */
const BENCH = TOOLS.filter(t => t.id !== 'audio');
/**
 * The pinned workbench items as stored in preferences.
 * @returns {Array<string>} Item ids
 */
function readPins() {
  try { return JSON.parse(load('pins', '["notes","quiz","flash"]')); } catch (e) { return ['notes', 'quiz', 'flash']; }
}
let pinnedIds = readPins();
const groups = ['輸入理解', '結構提煉', '主動提取'];
let currentTool = 'notes';
const readerContent = $('#readerContent');

$('#benchTiles').innerHTML = BENCH.map(t => `<div class="tile" role="button" tabindex="0" data-tool="${t.id}" style="--hue:var(${t.hue})"><span class="tile-name">${t.name}</span><span class="tile-meta" data-meta="${t.id}"></span><button class="pin-btn" data-pin="${t.id}" aria-label="釘選${t.name}"><i class="icon-pin"></i></button></div>`).join('') + '<p class="pin-empty">還沒有釘選的項目。切到「全景矩陣」，點卡片右上角的圖釘即可釘選。</p>';
$('#benchTiles').insertAdjacentHTML('afterend', '<p class="hint order-hint">拖曳卡片可以調整順序（鍵盤：Alt + 方向鍵），所有排列方式都會跟著這個順序。</p>');
/* Order: users drag tiles to reorder; every arrangement follows the same order */
const DEFAULT_ORDER = BENCH.map(t => t.id);
const DEFAULT_PINS = ['notes', 'quiz', 'flash'];
/**
 * The user's item order as stored in preferences (the default when the set of items changed).
 * @returns {Array<string>} Item ids
 */
function readOrder() {
  try {
    const o = JSON.parse(load('order', 'null'));
    if (Array.isArray(o) && o.length === DEFAULT_ORDER.length && DEFAULT_ORDER.every(id => o.includes(id))) return o;
  } catch (e) { /* stored value unreadable: use the default */ }
  return [...DEFAULT_ORDER];
}
let order = readOrder();
$('#triad').innerHTML = groups.map((g, gi) => `<div class="triad-group"><span class="eyebrow">${gi + 1}　${g}</span><div class="chips">${BENCH.filter(t => t.group === gi).map(t => `<button class="chip" data-tool="${t.id}" style="--hue:var(${t.hue})">${t.name}</button>`).join('')}</div></div>`).join('');
/**
 * Put tiles and triad chips in the user's order, then refresh the pinned list.
 * @param {boolean} persist Remember the order
 */
function applyOrder(persist = true) {
  const tiles = $('#benchTiles'), empty = $('.pin-empty', tiles);
  order.forEach(id => tiles.insertBefore($(`.tile[data-tool="${id}"]`, tiles), empty));
  $$('#triad .chips').forEach(c => order.forEach(id => { const ch = $(`[data-tool="${id}"]`, c); if (ch) c.append(ch); }));
  renderPins();
  if (persist) save('order', JSON.stringify(order));
}
/**
 * Move one workbench item to a new position in the order (tiles glide there).
 * @param {string} id Item id
 * @param {number} to New index
 */
function moveTool(id, to) {
  const from = order.indexOf(id); if (from < 0 || to < 0 || to >= order.length || from === to) return;
  order.splice(from, 1); order.splice(to, 0, id);
  flip($$('#benchTiles .tile'), () => applyOrder());
}
let dragId = null;
const tilesEl = $('#benchTiles');
$$('.tile', tilesEl).forEach(t => { t.draggable = true; });
tilesEl.addEventListener('dragstart', e => { const t = e.target.closest('.tile'); if (!t) return; dragId = t.dataset.tool; t.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', dragId); });
tilesEl.addEventListener('dragover', e => { const t = e.target.closest('.tile'); if (!t || !dragId) return; e.preventDefault(); $$('.drop-target', tilesEl).forEach(x => x !== t && x.classList.remove('drop-target')); if (t.dataset.tool !== dragId) t.classList.add('drop-target'); });
tilesEl.addEventListener('drop', e => { const t = e.target.closest('.tile'); e.preventDefault(); if (t && dragId) moveTool(dragId, order.indexOf(t.dataset.tool)); });
tilesEl.addEventListener('dragend', () => { dragId = null; $$('.dragging, .drop-target', tilesEl).forEach(x => x.classList.remove('dragging', 'drop-target')); });
tilesEl.addEventListener('keydown', e => {
  const t = e.target.closest('.tile'); if (!t || !e.altKey) return;
  const d = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[e.key]; if (!d) return;
  e.preventDefault(); const id = t.dataset.tool; moveTool(id, order.indexOf(id) + d); $(`.tile[data-tool="${id}"]`, tilesEl).focus();
});
/** Apply the pinned set: mark tiles, list the rest as chips, remember the choice. */
function renderPins() {
  $$('#benchTiles .tile').forEach(t => {
    const on = pinnedIds.includes(t.dataset.tool);
    t.classList.toggle('pinned', on);
    $('.pin-btn', t).setAttribute('aria-label', (on ? '取消釘選' : '釘選') + $('.tile-name', t).textContent);
  });
  const rest = order.map(id => BENCH.find(t => t.id === id)).filter(t => !pinnedIds.includes(t.id));
  $('#moreRow').innerHTML = rest.length ? `<span class="small muted">未釘選　點卡片右上角的圖釘可以增減常用項目</span>` + rest.map(t => `<button class="chip${t.id === currentTool ? ' on' : ''}" data-tool="${t.id}" style="--hue:var(${t.hue})">${t.name}</button>`).join('') : '';
  $('#bench').classList.toggle('no-pins', !BENCH.some(t => pinnedIds.includes(t.id) && !($('#paneStudy').dataset.layout === 'split' && t.id === 'notes')));
  save('pins', JSON.stringify(pinnedIds));
}
$('#bench').addEventListener('click', e => {
  const pin = e.target.closest('[data-pin]');
  if (pin) { const id = pin.dataset.pin; pinnedIds = pinnedIds.includes(id) ? pinnedIds.filter(x => x !== id) : [...pinnedIds, id]; renderPins(); return; }
  const b = e.target.closest('[data-tool]'); if (b) selectTool(b.dataset.tool);
});
$('#benchTiles').addEventListener('keydown', e => { const t = e.target.closest('.tile'); if (t && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); selectTool(t.dataset.tool); } });


/* Feature panels are loaded once per lecture; switching items back and forth keeps a quiz in progress */
let loadedFor = {};
/**
 * Run a panel loader unless it already ran for the current course and lecture.
 * @param {string} name Panel name
 * @param {function(): *} fn Loader
 */
function ensureLoaded(name, fn) {
  if (!currentStudyCourse) return;
  const key = `${currentStudyCourse.code}|${activeStudyLectureNo}`;
  if (loadedFor[name] === key) return;
  loadedFor[name] = key;
  fn();
}
/** Load the lecture PDF reader (it lives in the notes item, or in its own card in 雙欄). */
function ensureReader() {
  if (typeof loadReader === 'function') ensureLoaded('notes', loadReader);
}
/** Put every feature panel back in its hidden home (so moving them never destroys their state). */
function parkPanels() {
  $('#readerHome').append(readerContent);
  ['panelQuiz', 'panelFlash', 'panelReports', 'panelTutor'].forEach(id => $('#panelHome').append($('#' + id)));
}
/**
 * Select a workbench item: highlight it in every arrangement and show its panel in the stage.
 * @param {string} id Workbench item id
 */
function selectTool(id) {
  if (id === 'notes' && $('#paneStudy').dataset.layout === 'split') {
    // in 雙欄 the notes have their own card on the left
    ensureReader();
    $('#readerCard').scrollIntoView({ behavior: lowMotion() ? 'auto' : 'smooth', block: 'start' });
    return;
  }
  currentTool = id;
  const t = TOOLS.find(x => x.id === id) || TOOLS[0];
  $$('#bench [data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === id));
  const st = $('#benchStage');
  st.style.setProperty('--hue', `var(${t.hue})`);
  parkPanels();
  st.innerHTML = '';
  if (id === 'notes') {
    st.append(readerContent);
    ensureReader();
  } else {
    st.append($('#' + PANEL_FOR[id]));
    if (id === 'quiz') ensureLoaded('quiz', () => loadQuizForChapter(null));
    else if (id === 'flash') ensureLoaded('flash', loadFlashcardsViewer);
    else if (id === 'tutor') ensureLoaded('tutor', loadTutor);
    if (REPORT_GROUPS[id]) currentReportGroup = REPORT_GROUPS[id];
    // the report viewer is shared: show this item's output again when coming back from another report item
    if (REPORT_GROUPS[id] && loadedFor.reportShown !== id) { loadedFor.reportShown = id; loadReportInViewer(REPORT_GROUPS[id][0]); }
  }
  st.style.animation = 'none'; void st.offsetWidth; st.style.animation = '';
  if (currentStudyCourse && typeof rememberPlace === 'function') rememberPlace({ tab: TAB_FOR[id] });
  renderPins();
  requestAnimationFrame(refreshThumbs);
}
/** Write each item's status (generated, queued, missing) under its name. */
function updateToolMeta() {
  $$('[data-meta]').forEach(el => { el.textContent = toolMeta(el.dataset.meta); });
}

/**
 * Called whenever the current lecture changes: titles, item status, key points, audio and the open panel.
 */
function onLectureChanged() {
  loadedFor = {};
  const course = currentStudyCourse, no = activeStudyLectureNo;
  $('#crumbs').innerHTML = course
    ? `課程　/　${escHtml(course.code)} ${escHtml(course.name)}　/　<b>${lectureName(no)}${no !== null ? '　' + escHtml(lectureTopic(no)) : ''}</b>`
    : '課程';
  $('#readerEyebrow').textContent = `${lectureName(no)}　講義`;
  updateToolMeta();
  loadSideKeypoints();
  loadLectureAudio();
  if ($('#paneStudy').dataset.layout === 'split') ensureReader();
  selectTool(currentTool === 'notes' && $('#paneStudy').dataset.layout === 'split' ? 'report' : currentTool);
}

/**
 * Called after the course data changes (a quiz saved, a course switched): refresh what shows numbers.
 */
function onStudyDataChanged() {
  updateToolMeta();
  renderContinue();
}

/* ---------- 本講重點: the key points of the lecture; a click opens the notes at that sentence ---------- */
let sidePoints = [];
/** Load and list the current lecture's key points (most important first). */
async function loadSideKeypoints() {
  const box = $('#sideKeypoints');
  const course = currentStudyCourse, no = activeStudyLectureNo;
  if (!course) { box.innerHTML = ''; return; }
  if (no === null) { box.innerHTML = '<p class="small muted">整門課沒有單一講義。選一講後，這裡會列出它的重點。</p>'; return; }
  box.innerHTML = '<p class="loading-line">讀取重點中…</p>';
  try {
    const res = await fetch(`/api/courses/${encodeURIComponent(course.code)}/lectures/${no}/key-points`);
    sidePoints = res.ok ? (await res.json()).points || [] : [];
  } catch (e) {
    sidePoints = [];
  }
  if (activeStudyLectureNo !== no) return;
  if (!sidePoints.length) {
    box.innerHTML = '<p class="small muted" style="margin-bottom:12px">還沒有重點。請 Gemini Notebook 從講義挑出重點，並在課件上標出原文（只會問一次）。</p><button class="btn btn-soft" onclick="openNotesAndGenerate()">產生重點</button>';
    return;
  }
  const ranked = sidePoints.map((p, i) => ({ ...p, i })).sort((a, b) => b.importance - a.importance || a.i - b.i).slice(0, 8);
  box.innerHTML = `<ul class="keypoints">${ranked.map(p => `<li data-point="${p.i}"><span>${escHtml(p.note || p.quote)}</span></li>`).join('')}</ul>`;
}
/**
 * Open the notes and wait until the PDF pages exist, then run a callback.
 * @param {function(): void} then Called when the reader is ready (or after 6 seconds)
 */
function openNotes(then) {
  selectTool('notes');
  const t0 = performance.now();
  /**
   * Check every 150 ms whether the PDF pages exist; then (or after 6 seconds) run the callback.
   */
  const wait = () => {
    if ($('#readerPage-1') || performance.now() - t0 > 6000) { then(); return; }
    setTimeout(wait, 150);
  };
  wait();
}
/** Open the notes and ask Gemini Notebook for the key points. */
function openNotesAndGenerate() {
  openNotes(() => { generateKeyPoints(false).then(() => loadSideKeypoints()); });
}
$('#sideKeypoints').addEventListener('click', e => {
  const li = e.target.closest('li[data-point]'); if (!li) return;
  const i = +li.dataset.point;
  openNotes(() => jumpToPoint(i));
});

/** Place the study parts for the chosen layout: 主舞台 (stage) or 雙欄 (split). */
/* Each layout remembers where its blocks are (users drag the handle on top of a block) */
const BLOCK_DEFAULTS = {
  stage: { main: ['bench'], side: ['playerCard', 'sideInfo'] },
  split: { main: ['readerCard'], side: ['playerCard', 'bench'] },
  stack: { main: ['playerCard', 'bench'], side: [] },
};
/**
 * The remembered block arrangement for a layout, falling back to its default.
 * @param {string} v Layout: stage | split | stack
 * @returns {{main: Array<string>, side: Array<string>}} Block ids per column
 */
function blocksFor(v) {
  const def = BLOCK_DEFAULTS[v], ids = [...def.main, ...def.side].sort().join();
  try { const b = JSON.parse(load('blocks.' + v, 'null')); if (b && [...b.main, ...b.side].sort().join() === ids) return b; } catch (e) {}
  return { main: [...def.main], side: [...def.side] };
}
/**
 * Place the study blocks for a layout (主舞台, 雙欄 or 上下) and refresh the columns and the open item.
 * @param {string} v Layout: stage | split | stack
 */
function applyLayout(v) {
  const main = $('#studyMain'), side = $('#studySide'), parts = $('#studyParts'), ps = $('#paneStudy');
  ps.dataset.layout = v;
  const b = blocksFor(v);
  $$('.blk').forEach(el => parts.append(el));
  b.main.forEach(id => main.append($('#' + id)));
  b.side.forEach(id => side.append($('#' + id)));
  ps.classList.toggle('side-empty', v !== 'stack' && b.side.length === 0);
  $('#benchTitle').textContent = v === 'split' ? '學習產出物' : '講義與學習產出物';
  if (v === 'split') selectTool(currentTool === 'notes' ? 'report' : currentTool);
  else selectTool(currentTool === 'report' ? 'notes' : currentTool);
  renderPins();
  applyColumns($('#paneStudy'));
  updateMini();
  requestAnimationFrame(() => { sizeCanvases(); refreshThumbs(); updateSticky(); });
}
/* Block drag and drop between and within columns */
let dragBlk = null;
document.addEventListener('dragstart', e => {
  const g = e.target.closest && e.target.closest('.blk-grip'); if (!g) return;
  const blk = g.closest('.blk'); dragBlk = blk.id; blk.classList.add('blk-dragging');
  e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', blk.id);
  try { e.dataTransfer.setDragImage(blk, 40, 20); } catch (err) {}
});
/**
 * Which block the pointer is above (insert before it), or null for the end of the column.
 * @param {HTMLElement} col Column element
 * @param {number} y Pointer y position
 * @returns {HTMLElement|null} Block to insert before
 */
function blockBefore(col, y) {
  return $$(':scope > .blk', col).filter(b => b.id !== dragBlk).find(b => { const r = b.getBoundingClientRect(); return y < r.top + r.height / 2; }) || null;
}
/**
 * Move a block to a column (before another block, or at the end) and remember it for this layout.
 * @param {string} id Block id
 * @param {boolean} toSide True for the right column
 * @param {string|null} beforeId Block to insert before (null = end)
 */
function moveBlock(id, toSide, beforeId) {
  const v = $('#paneStudy').dataset.layout, b = blocksFor(v);
  b.main = b.main.filter(x => x !== id); b.side = b.side.filter(x => x !== id);
  const target = toSide ? b.side : b.main;
  target.splice(beforeId && target.includes(beforeId) ? target.indexOf(beforeId) : target.length, 0, id);
  if (!b.main.length) b.main = b.side.splice(0, 1);
  save('blocks.' + v, JSON.stringify(b));
  flip($$('.blk'), () => applyLayout(v));
}
$$('#studyMain, #studySide').forEach(col => {
  col.addEventListener('dragover', e => {
    if (!dragBlk) return; e.preventDefault();
    $$('.drop-before, .drop-end').forEach(x => x.classList.remove('drop-before', 'drop-end'));
    const before = blockBefore(col, e.clientY);
    if (before) before.classList.add('drop-before'); else col.classList.add('drop-end');
  });
  col.addEventListener('drop', e => {
    if (!dragBlk) return; e.preventDefault();
    const before = blockBefore(col, e.clientY);
    moveBlock(dragBlk, col.id === 'studySide', before && before.id); notify('已移動區塊');
  });
});
document.addEventListener('dragend', () => { dragBlk = null; $$('.blk-dragging, .drop-before, .drop-end').forEach(x => x.classList.remove('blk-dragging', 'drop-before', 'drop-end')); });

/** Sticky columns only while they fit the window, so nothing needs an inner scrollbar. */
function updateSticky() {
  $$('.study-side, .queue > .side-col').forEach(el => { el.classList.remove('no-stick'); el.classList.toggle('no-stick', el.offsetHeight > innerHeight - 32); });
}
window.addEventListener('resize', updateSticky);
new ResizeObserver(updateSticky).observe($('#studySide'));

/* ---------- 研讀總覽: greeting, today's choices, the continue card ---------- */
/** Greeting for the time of day with the user's initials. */
function renderGreeting() {
  const h = new Date().getHours();
  const word = h < 5 ? '夜深了' : h < 11 ? '早安' : h < 18 ? '午安' : '晚安';
  let name = '';
  try { const a = JSON.parse(load('avatar', '{"type":"text","value":"LK"}')); if (a.type === 'text') name = a.value; } catch (e) { name = ''; }
  $('#greet').textContent = name ? `${word}，${name}` : word;
}
/** Update the date and time on 今日打卡 (every 15 seconds). */
function tickClock() {
  const now = new Date();
  $('#clockTime').textContent = now.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', hour12: false });
  $('#clockDate').textContent = now.toLocaleDateString('zh-TW', { month: 'long', day: 'numeric', weekday: 'long' });
}
tickClock();
setInterval(tickClock, 15000);
/** Show the remembered 今天要讀幾講 and 專注時間 choices. */
function applyTodayChoices() {
  const goal = load('goal', '1');
  $$('#goalOptions button').forEach(x => x.classList.toggle('on', x.dataset.goal === goal));
  const focusMin = typeof todayFocus === 'function' ? todayFocus() : 25;
  $('#focusRange').value = focusMin; $('#focusMin').textContent = focusMin;
}
$('#goalOptions').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  $$('#goalOptions button').forEach(x => x.classList.toggle('on', x === b));
  save('goal', b.dataset.goal);
});
// today only: the habit itself is changed in 設計與自訂 → 專注習慣
$('#focusRange').addEventListener('input', e => {
  $('#focusMin').textContent = e.target.value;
  save('focusToday', JSON.stringify({ date: new Date().toDateString(), min: parseInt(e.target.value, 10) }));
  if (typeof renderPomo === 'function' && !pomo.total) renderPomo();
});
/** The "continue where you stopped" card: last lecture and page, with the audio position. */
function renderContinue() {
  const course = currentStudyCourse;
  const go_ = $('#contGo');
  if (!course) {
    $('#contEyebrow').textContent = '開始使用';
    $('#contTitle').textContent = currentCoursesList.length ? '選一門課開始' : '還沒有課程';
    $('#contSub').textContent = currentCoursesList.length ? '' : '到「批次排程」加入放講義 PDF 的資料夾';
    go_.textContent = currentCoursesList.length ? '進入研讀' : '加入課程';
    go_.onclick = () => (currentCoursesList.length ? go('studio') : (go('queue'), openAddModal()));
    return;
  }
  const place = typeof savedPlace === 'function' ? savedPlace() : null;
  const lec = place && place.lecture !== undefined ? place.lecture : activeStudyLectureNo;
  let audioAt = '';
  try {
    const a = JSON.parse(load(`audio:${course.code}:${lec === null ? 'course' : lec}`, 'null'));
    if (a && a.t > 5) audioAt = `語音摘要停在 ${fmt(a.t)}`;
  } catch (e) { audioAt = ''; }
  const tabName = place && place.tab && typeof TAB_NAMES !== 'undefined' ? TAB_NAMES[place.tab] : '';
  $('#contEyebrow').textContent = place ? '繼續上次的進度' : '開始研讀';
  $('#contTitle').textContent = `${lectureName(lec)}　${lec === null ? '全課跨章總複習' : lectureTopic(lec)}`;
  $('#contSub').textContent = [tabName ? `上次在${tabName}` : '', place && place.answered ? `答到第 ${place.answered} 題` : '', audioAt].filter(Boolean).join('　·　');
  go_.textContent = place ? '繼續研讀' : '進入研讀';
  go_.onclick = () => { if (place && typeof resumePlace === 'function') resumePlace(); else { selectStudyLecture(lec); go('studio'); } };
}

/* ---------- 今日學習卡 (弱點複習) and the review boxes ---------- */
let deck = [], deckIdx = 0;
/**
 * Draw review boxes (1, 3, 7, 14, 30 days) for the due cards.
 * @param {HTMLElement} box Container
 * @param {Array<{stage: number}>} items Due items
 */
function renderLeitner(box, items) {
  const counts = [0, 0, 0, 0, 0];
  items.forEach(i => { counts[Math.max(0, Math.min(4, (i.stage || 0) - 1))] += 1; });
  const max = Math.max(1, ...counts);
  box.innerHTML = ['1 天', '3 天', '7 天', '14 天', '30 天'].map((label, k) =>
    `<div title="${counts[k]} 張"><i style="height:${Math.round(4 + 86 * counts[k] / max)}%"></i><span>${label}</span></div>`).join('');
}
/** Load the cards due now; fill the review deck, both review-box charts and the overview label. */
async function loadReviewCards() {
  if (!currentStudyCourse) return;
  let due = [];
  try {
    const res = await fetch(`/api/courses/${currentStudyCourse.code}/study/reviews/due`);
    due = res.ok ? await res.json() : [];
  } catch (e) { due = []; }
  deck = due.filter(d => d.kind === 'flashcard');
  deckIdx = 0;
  renderLeitner($('#reviewLeitner'), due);
  renderLeitner($('#dueLeitner'), due);
  $('#dueLabel').textContent = `間隔複習（今天到期 ${deck.length} 張）`;
  renderReviewDeck();
}
/** Draw the review card on screen (or a note when nothing is due). */
function renderReviewDeck() {
  const box = $('#reviewDeck');
  const left = deck.length - deckIdx;
  $('#cardCount').textContent = left > 0 ? `還有 ${left} 張` : '';
  if (left <= 0) {
    box.innerHTML = `<div class="empty-state">${deck.length ? '今天到期的學習卡都複習完了。' : '目前沒有到期的學習卡。'}<br><span class="small">在研讀工作室翻學習卡並評估「記得 / 不記得」後，它們會依間隔回到這裡。</span><br><button class="btn btn-soft" onclick="switchStudyTab('flashcards')">去翻這一講的學習卡</button></div>`;
    return;
  }
  const c = deck[deckIdx];
  box.innerHTML = `<div class="flashcard" id="reviewFlash" role="button" tabindex="0" aria-label="翻面"><div class="flashcard-inner"><div class="face">${escHtml(c.front)}</div><div class="face back">${escHtml(c.back)}</div></div></div>
    <p class="small muted" style="text-align:center;margin-top:8px">${lectureName(c.lecture_no ?? null)}　·　點卡片翻面</p>
    <div class="row section-gap" style="justify-content:center;flex-wrap:wrap"><button class="btn btn-ghost fc-rate" data-rate="0">忘記了</button><button class="btn btn-primary fc-rate" data-rate="1">記得</button></div>`;
}
$('#reviewDeck').addEventListener('click', async e => {
  const card = $('#reviewFlash');
  if (e.target.closest('#reviewFlash')) { card.classList.toggle('flipped'); return; }
  const btn = e.target.closest('.fc-rate'); if (!btn || !card) return;
  const remembered = btn.dataset.rate === '1', c = deck[deckIdx];
  $$('.fc-rate').forEach(b => { b.disabled = true; });
  await rateCard(c, remembered, c.lecture_no ?? null);
  announce(remembered ? '記得，下次間隔拉長' : '已標為忘記，10 分鐘後再出現');
  /**
   * Show the next due card, rising in.
   */
  const next = () => { deckIdx += 1; renderReviewDeck(); const n = $('#reviewFlash'); if (n && !lowMotion()) { n.classList.add('card-in'); setTimeout(() => n.classList.remove('card-in'), 520); } };
  if (lowMotion()) next(); else { card.classList.add(remembered ? 'out-right' : 'out-left'); setTimeout(next, 420); }
});
/** Open today's due cards on the review page. */
function startReviewSession() {
  go('review'); setChoice('reviewTab', 'cards', false); loadReviewCards();
}

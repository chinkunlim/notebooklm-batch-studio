/* Gemini Notebook 學習工作室 — v05 shell, part 1 (SPEC-009, ADR-008): preferences, workbench item data,
   segmented controls and the Dock indicator, the floating expand button, choices, motion helpers,
   page navigation with the flying record, and progress rings. Preferences are kept in this browser
   (localStorage keys "v05.*"). The shell continues in studio-player.js, studio-bench.js and
   studio-start.js (which starts the page); feature functions come from the scripts loaded before. */

/* Preferences are recorded on this computer (GET / PUT /api/preferences, SQLite in DATA_DIR, ADR-009).
   This visit reads them from memory; localStorage ("v05.*") is only a cache so the first paint already
   has the right palette. Changes are sent to the server in small batches. */
const mem = {};
let prefQueue = {}, prefTimer = 0;
// nothing is sent until the recorded preferences have arrived (or the server did not answer), and not
// while preferences are being applied, so a stale browser cache never overwrites the recorded copy
let prefsReady = false, prefMute = false;
/**
 * A preference key the server accepts (letters, digits and . _ : -); other characters are escaped.
 * @param {string} key Preference name
 * @returns {string} Safe key
 */
function prefKey(key) {
  return String(key).replace(/[^A-Za-z0-9._:-]/g, c => '_' + c.codePointAt(0).toString(16)).slice(0, 120);
}
/**
 * Read a preference (memory first, then the browser cache).
 * @param {string} key Preference name without the "v05." prefix
 * @param {*} fallback Value when nothing is stored
 * @returns {string|*} Stored value or the fallback
 */
function load(key, fallback) {
  const k = prefKey(key);
  if (k in mem) return mem[k];
  try { return localStorage.getItem('v05.' + k) ?? fallback; } catch (e) { return fallback; }
}
/**
 * Store a preference here and on this computer's server.
 * @param {string} key Preference name without the "v05." prefix
 * @param {*} value Value (kept as text)
 */
function save(key, value) {
  const k = prefKey(key);
  mem[k] = String(value);
  try { localStorage.setItem('v05.' + k, value); } catch (e) { /* cache only */ }
  queuePref(k, String(value));
}
/**
 * Forget a preference so its default applies again (here and on the server).
 * @param {string} key Preference name without the "v05." prefix
 */
function forget(key) {
  const k = prefKey(key);
  delete mem[k];
  try { localStorage.removeItem('v05.' + k); } catch (e) { /* cache only */ }
  queuePref(k, null);
}
/**
 * Add one change to the next batch sent to the server (sent 300 ms after the last change).
 * @param {string} key Safe preference key
 * @param {string|null} value New value, or null to delete
 */
function queuePref(key, value) {
  if (!prefsReady || prefMute) return;
  prefQueue[key] = value;
  clearTimeout(prefTimer);
  prefTimer = setTimeout(() => flushPrefs(false), 300);
}
/**
 * Send the waiting preference changes to the server.
 * @param {boolean} keepalive True when the page is closing (the request still finishes)
 */
function flushPrefs(keepalive) {
  const values = prefQueue;
  if (!Object.keys(values).length) return;
  prefQueue = {};
  fetch('/api/preferences', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ values }), keepalive })
    .then(res => { if (!res.ok) console.warn('Preferences not saved', res.status); })
    .catch(() => { prefQueue = { ...values, ...prefQueue }; });  // server not answering: try again with the next change
}
addEventListener('pagehide', () => flushPrefs(true));
/**
 * Load the preferences recorded on this computer into memory and the browser cache.
 * The first time (nothing recorded yet) this browser's own settings are uploaded instead, so they are kept.
 * @returns {Promise<boolean>} True when the server answered
 */
async function syncPreferences() {
  let server;
  try {
    const res = await fetch('/api/preferences');
    server = res.ok ? (await res.json()).values || {} : null;
  } catch (e) {
    server = null;
  }
  prefsReady = true;
  if (!server) return false;  // server not answering: keep using the browser cache
  let local = {};
  try { Object.keys(localStorage).filter(k => k.startsWith('v05.')).forEach(k => { local[k.slice(4)] = localStorage.getItem(k); }); } catch (e) { local = {}; }
  if (!Object.keys(server).length && Object.keys(local).length) {
    Object.entries(local).forEach(([k, v]) => queuePref(prefKey(k), v));
    flushPrefs(false);
    return true;
  }
  Object.keys(mem).forEach(k => delete mem[k]);
  Object.assign(mem, server);
  try {
    Object.keys(local).filter(k => !(k in server)).forEach(k => localStorage.removeItem('v05.' + k));
    Object.entries(server).forEach(([k, v]) => localStorage.setItem('v05.' + k, v));
  } catch (e) { /* cache only */ }
  return true;
}
/**
 * Read a preference (name used by the feature scripts).
 * @param {string} key Preference name without the "v05." prefix
 * @param {string} fallback Value when nothing is stored
 * @returns {string} Stored value or the fallback
 */
function prefLoad(key, fallback) { return load(key, fallback); }
/**
 * Store a preference (name used by the feature scripts).
 * @param {string} key Preference name without the "v05." prefix
 * @param {*} value Value to store (kept as text)
 */
function prefSave(key, value) { save(key, value); }

/**
 * First element matching a selector.
 * @param {string} s CSS selector
 * @param {ParentNode} r Where to search (the document by default)
 * @returns {Element|null} Element
 */
const $ = (s, r = document) => r.querySelector(s);
/**
 * Every element matching a selector, as an array.
 * @param {string} s CSS selector
 * @param {ParentNode} r Where to search (the document by default)
 * @returns {Array<Element>} Elements
 */
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const root = document.documentElement;
const darkMQ = matchMedia('(prefers-color-scheme: dark)');
let modePref = 'auto';
darkMQ.addEventListener('change', () => { if (modePref === 'auto') handlers.mode('auto'); });

/* ---------- Workbench items: 講義 + the outputs + the tutor (audio is the player itself) ---------- */
const TOOLS = [
  { id: 'notes', name: '講義', group: 0, hue: '--accent' },
  { id: 'video', name: '影片摘要', group: 0, hue: '--h-video' },
  { id: 'report', name: '報告', group: 0, hue: '--h-report' },
  { id: 'mindmap', name: '心智圖', group: 1, hue: '--h-mindmap' },
  { id: 'infographic', name: '資訊圖表', group: 1, hue: '--h-infographic' },
  { id: 'slides', name: '簡報', group: 1, hue: '--h-slides' },
  { id: 'table', name: '資料表', group: 1, hue: '--h-table' },
  { id: 'quiz', name: '測驗', group: 2, hue: '--h-quiz' },
  { id: 'flash', name: '學習卡', group: 2, hue: '--h-flash' },
  { id: 'tutor', name: 'AI 家教', group: 2, hue: '--primary' },
];
/** Artifact types behind each workbench item (lecture names; course_ is added for the whole course). */
const TOOL_TYPES = {
  video: ['video'], report: ['study_guide', 'reports_study_guide', 'reports_concept_explanation', 'reports_briefing', 'reports_blog_post'],
  mindmap: ['mind_map'], infographic: ['infographic'], slides: ['slide_deck'], table: ['data_table'],
  quiz: ['quiz_1', 'quiz_2', 'quiz_3', 'quiz_academic', 'quiz_concept', 'mock_exam'], flash: ['flashcards'],
};
/** Report viewer kinds (REPORT_KINDS in studio-app.js) offered by each item. */
const REPORT_GROUPS = { report: ['guide', 'concept', 'briefing', 'blog'], video: ['video'], mindmap: ['mindmap'], infographic: ['infographic'], slides: ['slides'], table: ['table'] };
/** Feature panel node for each item (notes uses the reader). */
const PANEL_FOR = { quiz: 'panelQuiz', flash: 'panelFlash', tutor: 'panelTutor', video: 'panelReports', report: 'panelReports', mindmap: 'panelReports', infographic: 'panelReports', slides: 'panelReports', table: 'panelReports' };
/** Older tab names (used by rememberPlace / resumePlace) for each item. */
const TAB_FOR = { notes: 'reader', quiz: 'quiz', flash: 'flashcards', tutor: 'tutor', video: 'reports', report: 'reports', mindmap: 'reports', infographic: 'reports', slides: 'reports', table: 'reports' };

/**
 * One-line status of an item for the current lecture, e.g. "已生成 v2" or "尚未生成".
 * @param {string} id Workbench item id
 * @returns {string} Status text
 */
function toolMeta(id) {
  if (!currentStudyCourse) return '';
  const lec = activeStudyLectureNo;
  if (id === 'notes') return lec === null ? '請先選一講' : '講義 PDF 與重點';
  if (id === 'tutor') return '用問題引導你想通';
  const wanted = TOOL_TYPES[id].map(t => (lec === null ? `course_${t}` : t));
  const jobs = (currentStudyCourse.jobs || []).filter(j => wanted.includes(j.artifact_type) && (lec === null ? j.lecture_no === null : j.lecture_no === lec));
  const done = jobs.filter(j => ['done', 'needs_review'].includes(j.status));
  if (done.length) {
    if (id === 'quiz') return `${new Set(done.map(j => j.artifact_type)).size} 份可作答`;
    const v = Math.max(...done.map(j => j.version || 1));
    return `已生成${v > 1 ? `　·　第 ${v} 版` : ''}`;
  }
  if (jobs.some(j => j.status === 'running')) return '生成中';
  if (jobs.some(j => ['pending', 'quota_wait'].includes(j.status))) return '排隊中';
  return '尚未生成';
}
/* ---------- Sliding thumbs (segmented controls + Dock pill) ---------- */
/**
 * Move a sliding thumb onto the active button of its segmented control.
 * @param {HTMLElement} thumb Thumb element
 * @param {HTMLElement} active Active button
 */
function placeThumb(thumb, active) {
  if (!thumb || !active || !active.offsetWidth) return;
  thumb.style.width = active.offsetWidth + 'px';
  thumb.style.height = active.offsetHeight + 'px';
  thumb.style.transform = `translate(${active.offsetLeft}px, ${active.offsetTop}px)`;
}
/** Place the selection tab on the active Dock item (page or 設計與自訂), reaching the Dock edge. */
/* Indicator: one piece made of the notch (a rounded tab in the page colour reaching from the Dock edge to the
   active icon, blended into the edge with fillets) and the green circle behind that icon. The icons never move;
   the whole piece slides to the active item. Local coordinates: u runs along the Dock edge, v points out of the
   Dock (v < 0 is inside). */
const IND = { f: 16, band: 56, N: 10, M: 24 };
/**
 * Points on a circle from angle a0 to a1 (degrees) in n segments.
 * @param {number} cu Centre along the Dock edge
 * @param {number} cv Centre across the Dock edge
 * @param {number} r Radius
 * @param {number} a0 Start angle
 * @param {number} a1 End angle
 * @param {number} n Segment count
 * @returns {Array<Array<number>>} Points
 */
function arcPts(cu, cv, r, a0, a1, n) {
  const out = [];
  for (let i = 0; i <= n; i++) { const a = (a0 + (a1 - a0) * i / n) * Math.PI / 180; out.push([cu + r * Math.cos(a), cv + r * Math.sin(a)]); }
  return out;
}
/**
 * Expanded indicator shape: a band reaching into the Dock (rounded far end), blended into the edge.
 * @param {number} L Band length
 * @returns {Array<Array<number>>} Points
 */
function bandShape(L) {
  const { band, f, N, M } = IND, r = band / 2;
  return [...arcPts(-(r + f), -f, f, 90, 0, N), [-r, -f], ...arcPts(0, -(L - r), r, 180, 360, M - 3), [r, -f], ...arcPts(r + f, -f, f, 180, 90, N)];
}
/** Place the selection indicator (notch + circle, one piece) on the active Dock item; the icons stay still. */
function placeDockPill() {
  const ind = $('#dockPill'), dock = $('.dock'), active = $('.dock .dock-btn.on');
  $$('.dock .dock-btn').forEach(b => { b.style.transform = ''; });
  if (!active || !active.offsetWidth || !dock.offsetWidth) { ind.style.opacity = '0'; return; }
  ind.style.opacity = '1';
  const horizontal = getComputedStyle(dock).flexDirection === 'row';
  let x = 0, y = 0, el = active;
  while (el && el !== dock) { x += el.offsetLeft; y += el.offsetTop; el = el.offsetParent; }
  const iconCx = x + 24, iconCy = y + active.offsetHeight / 2, W = dock.offsetWidth, r = IND.band / 2;
  // the tab's rounded end is centred on the icon, so the circle and the notch always line up
  const pts = bandShape(horizontal ? iconCy + r : W - iconCx + r);
  pts.push([pts[pts.length - 1][0], 4], [pts[0][0], 4]);
  const map = horizontal ? ([u, v]) => [u, -v] : ([u, v]) => [W + v, u];
  const dStr = 'M' + pts.map(p => map(p).map(n => n.toFixed(1)).join(' ')).join(' L') + ' Z';
  const path = $('.ind-path', ind);
  path.style.d = `path("${dStr}")`; path.setAttribute('d', dStr);
  $('.ind-dot', ind).style.transform = horizontal ? `translate(-24px, ${iconCy - 24}px)` : `translate(${iconCx - 24}px, -24px)`;
  ind.style.transform = horizontal ? `translateX(${x + active.offsetWidth / 2}px)` : `translateY(${iconCy}px)`;
}
/**
 * Expand or collapse the Dock (labels shown when expanded); the indicator follows every frame.
 * @param {boolean} on True to expand
 * @param {boolean} persist Remember the choice
 */
function setDockX(on, persist = true) {
  $('#app').classList.toggle('dock-x', on);
  const b = $('#btnDockX'); b.setAttribute('aria-label', on ? '收合側欄' : '展開側欄');
  $('i', b).className = on ? 'icon-panel-left-close' : 'icon-panel-left-open';
  $('.tip', b).textContent = on ? '收合側欄' : '展開側欄';
  if (persist) save('dockX', on);
  const ind = $('#dockPill'), dock = $('.dock'), t0 = performance.now();
  ind.classList.add('live'); dock.classList.add('live');
  const loop = now => {
    placeDockPill();
    if (now - t0 < 700) requestAnimationFrame(loop);
    else { ind.classList.remove('live'); dock.classList.remove('live'); refreshThumbs(); sizeCanvases(); }
  };
  requestAnimationFrame(loop);
}
$('#btnDockX').addEventListener('click', () => setDockX(!$('#app').classList.contains('dock-x')));
document.addEventListener('fullscreenchange', () => requestAnimationFrame(refreshThumbs));
/* Floating expand button */
let fabTarget = null;
/** Show the floating button when the visible page has a collapsed right column (wide screens only). */
function updateFab() {
  const fab = $('#sideFab'), view = $('.view.on');
  const wide = $('#app').offsetWidth > 1000 && !$('#app').classList.contains('focus');
  fabTarget = wide && view ? $$('.resizable.side-collapsed', view).find(e => !e.hidden && e.offsetParent) || null : null;
  fab.classList.toggle('show', !!fabTarget);
  if (fabTarget) placeFab();
}
/**
 * Corner position of the floating expand button inside the visible app area (24px from the edges, clear of the Dock).
 * @param {{h: string, v: string}} c Corner: h left/right, v top/bottom
 * @returns {{x: number, y: number}} Position
 */
function fabCorner(c) {
  const r = $('#app').getBoundingClientRect(), m = 24, size = 52, dockW = $('.dock').offsetWidth;
  const top = Math.max(r.top, 0) + m, bottom = Math.min(r.bottom, innerHeight) - m - size;
  return { x: c.h === 'left' ? r.left + dockW + m : r.right - m - size, y: c.v === 'top' ? top : bottom };
}
/** Put the floating button in its remembered corner (bottom right by default). */
function placeFab() {
  let c; try { c = JSON.parse(load('fabCorner', 'null')); } catch (e) { c = null; }
  const p = fabCorner(c || { h: 'right', v: 'bottom' }), fab = $('#sideFab');
  fab.style.left = p.x + 'px'; fab.style.top = p.y + 'px';
}
(() => {
  const fab = $('#sideFab'); let start = null, moved = false;
  fab.addEventListener('pointerdown', e => { start = { x: e.clientX, y: e.clientY, l: fab.offsetLeft, t: fab.offsetTop }; moved = false; fab.setPointerCapture(e.pointerId); });
  fab.addEventListener('pointermove', e => {
    if (!start) return;
    const dx = e.clientX - start.x, dy = e.clientY - start.y;
    if (!moved && Math.hypot(dx, dy) < 5) return;
    moved = true; fab.classList.add('dragging');
    fab.style.left = (start.l + dx) + 'px'; fab.style.top = (start.t + dy) + 'px';
  });
  fab.addEventListener('pointerup', () => {
    if (!start) return;
    if (moved) {
      // let go: glide into the nearest corner and remember it
      const r = $('#app').getBoundingClientRect(), cx = fab.offsetLeft + 26, cy = fab.offsetTop + 26;
      const midY = (Math.max(r.top, 0) + Math.min(r.bottom, innerHeight)) / 2;
      save('fabCorner', JSON.stringify({ h: cx < (r.left + r.right) / 2 ? 'left' : 'right', v: cy < midY ? 'top' : 'bottom' }));
      fab.classList.add('snapping'); placeFab(); setTimeout(() => fab.classList.remove('snapping'), 480);
    } else if (fabTarget) {
      $(':scope > .col-resizer .col-toggle', fabTarget).click();
    }
    start = null; fab.classList.remove('dragging');
  });
  addEventListener('scroll', () => fabTarget && placeFab(), { passive: true });
  addEventListener('resize', () => fabTarget && placeFab());
})();
/** Segmented controls behave as radio groups for assistive technology. */
function ariaSegs() {
  $$('.seg').forEach(seg => {
    seg.setAttribute('role', 'radiogroup');
    $$('button', seg).forEach(b => { b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', b.classList.contains('on')); b.tabIndex = b.classList.contains('on') ? 0 : -1; });
  });
}
/**
 * Re-place every sliding thumb, the Dock indicator and the floating button (after layout changes).
 */
function refreshThumbs() {
  ariaSegs();
  updateFab();
  $$('.seg').forEach(seg => placeThumb($('.seg-thumb', seg), $('button.on', seg)));
  placeDockPill();
}
$$('.seg').forEach(seg => {
  const t = document.createElement('span'); t.className = 'seg-thumb'; seg.prepend(t);
  seg.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    setChoice(seg.dataset.seg, b.dataset.value);
  });
});
new ResizeObserver(() => refreshThumbs()).observe(document.body);


/* ---------- One place that applies every choice (keeps segs, cards and state in sync) ---------- */
const handlers = {
  pace: v => { $('#view-overview').dataset.pace = v; },
  mode: v => { modePref = v; root.dataset.mode = v === 'auto' ? (darkMQ.matches ? 'dark' : 'light') : v; vizColors(); },
  palette: v => { root.dataset.palette = PALETTES.some(p => p.id === v) || customPalettes.some(p => p.id === v) ? v : 'forest'; vizColors(); },
  style: v => {
    root.dataset.style = v;
    if (v === 'practice' && load('arr', null) === null) setChoice('arr', 'pinned', false);
    if (typeof renderFontControls === 'function') renderFontControls();  // 預設 pairing follows the style
  },
  arr: v => { $('#bench').dataset.arr = v; },
  skin: v => setSkin(v),
  speed: v => {
    player.speed = parseFloat(v); audio.playbackRate = player.speed;
    $('#speedBtn').textContent = v + '×'; $('#dpSpeed').textContent = v + '×';
    $$('#speedMenu button').forEach(b => b.classList.toggle('on', b.dataset.v === v));
  },
  layout: v => applyLayout(v),
  studioPane: v => { $('#paneCourses').hidden = v !== 'courses'; $('#paneStudy').hidden = v !== 'study'; updateMini(); requestAnimationFrame(sizeCanvases); },
  reviewTab: v => { $('#reviewMistakes').hidden = v !== 'mistakes'; $('#reviewCards').hidden = v !== 'cards'; },
};
const persisted = ['pace', 'mode', 'palette', 'style', 'arr', 'skin', 'speed', 'layout'];
/* The current design is the default; everything the user changes is remembered and can be restored in one click */
const DEFAULTS = { palette: 'forest', mode: 'auto', style: 'flow', arr: 'matrix', pace: 'relax', speed: '1', skin: 'vinyl', layout: 'stage' };
const COL_DEFAULTS = { stage: 28, split: 50, queue: 36, courses: 46, review: 50, reviewCards: 50 };
const COL_LABELS = { queue: '進行中', courses: '課程內容', review: '題目詳解', reviewCards: '複習盒' };
/**
 * Apply a choice everywhere: segmented controls, option cards and state.
 * @param {string} name Choice name, e.g. layout, palette, speed
 * @param {string} value Chosen value
 * @param {boolean} persist Remember it (only for the persisted choices)
 */
function setChoice(name, value, persist = true) {
  $$(`.seg[data-seg="${name}"] button`).forEach(b => b.classList.toggle('on', b.dataset.value === value));
  $$(`.opt-cards[data-opt="${name}"] .opt-card`).forEach(b => b.classList.toggle('on', b.dataset.value === value));
  (handlers[name] || (() => {}))(value);
  if (persist && persisted.includes(name)) save(name, value);
  requestAnimationFrame(refreshThumbs);
}
$$('.opt-cards[data-opt]').forEach(g => g.addEventListener('click', e => {
  const c = e.target.closest('.opt-card'); if (c) setChoice(g.dataset.opt, c.dataset.value);
}));

/* ---------- Motion helpers ---------- */
/** True when the user asked for less motion (system setting or 頁面動態 off). */
const lowMotion = () => root.dataset.motion === 'reduced' || matchMedia('(prefers-reduced-motion: reduce)').matches;
/**
 * Announce a short message to screen readers without showing anything.
 * @param {string} msg Message
 */
function announce(msg) { const el = $('#srLive'); el.textContent = ''; setTimeout(() => { el.textContent = msg; }, 30); }
/**
 * FLIP: let elements glide from their old place to the new one after `mutate` rearranges them.
 * @param {Array<HTMLElement>} els Elements that may move
 * @param {function(): void} mutate Change that moves them
 */
function flip(els, mutate) {
  if (lowMotion()) { mutate(); return; }
  const before = new Map(els.map(e => [e, e.getBoundingClientRect()]));
  mutate();
  els.forEach(e => {
    const a = before.get(e), b = e.getBoundingClientRect();
    if (!a || !b.width) return;
    const dx = a.left - b.left, dy = a.top - b.top;
    if (!dx && !dy) return;
    e.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], { duration: 450, easing: 'cubic-bezier(.22, 1, .36, 1)' });
  });
}
/** Count the overview numbers up from zero, once per visit. */

/**
 * Short confirmation message (same look as every other toast).
 * @param {string} msg Message
 */
function notify(msg) { showToast(msg, 'success', 2400); }

/* ---------- Navigation ---------- */
let currentView = 'overview';
/** The record in the Dock shows only while audio plays and the full player is not on screen. */
function updateMini() {
  const ps = $('#paneStudy'), card = $('#playerCard');
  const inSide = card.parentElement === $('#studySide');
  const playerShown = currentView === 'studio' && !ps.hidden && !(inSide && ps.classList.contains('side-collapsed'));
  const show = player.playing && !playerShown;
  const popOpen = $('#discPop').classList.contains('open');
  $('#discWrap').classList.toggle('show', show || popOpen);
}
const pageNames = { overview: '研讀總覽', studio: '研讀工作室', review: '弱點複習', queue: '批次排程', custom: '設計與自訂' };
/* Page change: the old page fades out, the window returns to the top while nothing is visible, and the
   new page rises in. The Dock never moves; its indicator glides on a soft curve that takes longer for a
   longer distance, so neighbouring pages feel as calm as far ones. */
const PAGE_OUT_MS = 240;
let pageTarget = null, pageTimer = 0;
/**
 * Make the Dock indicator glide to a page (duration grows with the distance travelled).
 * @param {string} view Page id
 */
function moveDockTo(view) {
  const btns = $$('.dock .dock-btn'), from = btns.findIndex(b => b.classList.contains('on'));
  const target = view === 'custom' ? $('#btnCustom') : $(`.dock-btn[data-view="${view}"]`);
  const steps = from < 0 ? 1 : Math.abs(btns.indexOf(target) - from);
  $('.dock').style.setProperty('--pill-dur', `${Math.min(1100, 620 + steps * 90)}ms`);
  btns.forEach(b => b.classList.toggle('on', b === target));
  placeDockPill();
}
/**
 * Show one page with a gentle fade (instant when motion is reduced); the playing record flies between places.
 * @param {string} view Page id: overview | studio | review | queue | custom
 */
function go(view) {
  if (!pageNames[view]) return;
  // going to the study page while the record sits in the Dock: the record flies back into the player
  if (view === 'studio' && view !== currentView && player.playing && $('#discWrap').classList.contains('show')) { backToPlayer(); return; }
  if (currentView === 'studio' && view !== 'studio' && player.playing && !$('#discWrap').classList.contains('show') && playerDisc()?.offsetParent) { toDock(view); return; }
  if (view === currentView && !pageTarget) { showView(view); return; }
  if (lowMotion()) { showView(view); scrollTo(0, 0); return; }
  moveDockTo(view);
  const leaving = $('.view.on');
  if (!pageTarget && leaving) leaving.classList.add('leaving');
  pageTarget = view;
  clearTimeout(pageTimer);
  pageTimer = setTimeout(() => {
    $$('.view.leaving').forEach(v => v.classList.remove('leaving'));
    scrollTo(0, 0);
    const next = pageTarget; pageTarget = null;
    showView(next);
  }, PAGE_OUT_MS);
}
/** The player's disc element for the current visual. */
const playerDisc = () => (skin === 'vinyl' ? $('#vinyl') : $('#visual .skin.on .viz-disc'));
/**
 * Fly a copy of the record between two places along a random curved path; it spins, lifts with a soft shadow and settles.
 * @param {DOMRect} from Start rectangle
 * @param {DOMRect|object} to End rectangle
 * @param {DOMRect} big Rectangle of the large end (the player disc)
 * @param {function(): void} onDone Called when it lands
 */
function flyDisc(from, to, big, onDone) {
  const d = big.width, clone = document.createElement('span');
  clone.className = `${miniClass()} spin fly-disc`; clone.innerHTML = skin === 'vinyl' ? '' : '<canvas aria-hidden="true"></canvas>';
  clone.style.cssText += `left:${big.left}px;top:${big.top}px;--d:${d}px;`;
  document.body.append(clone);
  if (skin !== 'vinyl') { sizeMini(clone); paintSkin($('canvas', clone), player.playing ? performance.now() : 0, player.playing ? 1 : 0.28); }
  const c = r => [r.left + r.width / 2, r.top + r.height / 2];
  const [x0, y0] = c(from), [x3, y3] = c(to), [bx, by] = c(big);
  const vx = x3 - x0, vy = y3 - y0, len = Math.hypot(vx, vy) || 1, nx = -vy / len, ny = vx / len;
  const side = Math.random() < 0.5 ? -1 : 1, bend = len * (0.28 + Math.random() * 0.3), lift = 60 + Math.random() * 90;
  const p1 = [x0 + vx * 0.2 + nx * bend * side, y0 + vy * 0.2 + ny * bend * side - lift];
  const p2 = [x0 + vx * 0.75 - nx * bend * 0.45 * side * Math.random(), y0 + vy * 0.75 - ny * bend * 0.45 * side - lift * 0.35];
  const s0 = from.width / d, s3 = to.width / d, spin = (skin === 'sine' || skin === 'led' ? 30 : 300 + Math.random() * 240) * side;
  const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const frames = [];
  for (let i = 0; i <= 30; i++) {
    const t = ease(i / 30), u = 1 - t;
    const x = u * u * u * x0 + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * x3;
    const y = u * u * u * y0 + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * y3;
    const sc = (s0 + (s3 - s0) * t) * (1 + 0.08 * Math.sin(Math.PI * t));
    const lifted = Math.sin(Math.PI * t);
    frames.push({ transform: `translate(${x - bx}px, ${y - by}px) rotate(${spin * t}deg) scale(${sc})`, filter: `drop-shadow(0 ${6 + 22 * lifted}px ${10 + 24 * lifted}px rgba(0,0,0,${0.25 + 0.15 * lifted}))` });
  }
  const anim = clone.animate(frames, { duration: 950 + Math.random() * 150, easing: 'linear' });
  anim.onfinish = () => { clone.remove(); onDone && onDone(); };
}
/** Small bounce when a record lands. */
const settle = el => el.animate([{ transform: 'scale(1.06)' }, { transform: 'scale(.98)' }, { transform: 'none' }], { duration: 380, easing: 'cubic-bezier(.22, 1, .36, 1)' });
/** Open the study page with the player visible; the Dock record flies out along a curve and grows into the player's disc. */
function backToPlayer() {
  const src = $('#dockDiscIcon').getBoundingClientRect();
  setDiscPop(false);
  showView('studio'); setChoice('studioPane', 'study', false);
  const ps = $('#paneStudy'), wasCollapsed = ps.classList.contains('side-collapsed') && $('#playerCard').parentElement === $('#studySide');
  if (wasCollapsed) $(':scope > .col-resizer .col-toggle', ps).click();
  if (lowMotion()) return;
  const top = $('#playerCard').getBoundingClientRect().top; if (top < 0 || top > innerHeight - 200) scrollTo({ top: 0 });
  playerDisc().style.visibility = 'hidden';
  setTimeout(() => {
    const el = playerDisc(), tr = el.getBoundingClientRect();
    if (!tr.width) { el.style.visibility = ''; return; }
    flyDisc(src, tr, tr, () => { el.style.visibility = ''; settle(el); sizeCanvases(); });
  }, wasCollapsed ? 720 : 60);
}
/**
 * Leaving the study page while playing: the player's record flies along a curve and shrinks into the Dock.
 * @param {string} view Page to show
 */
function toDock(view) {
  const el = playerDisc(), from = el.getBoundingClientRect();
  showView(view);
  if (lowMotion() || !from.width) return;
  const icon = $('#dockDiscIcon'), btn = $('#dockDisc').getBoundingClientRect(), wrap = $('#discWrap').getBoundingClientRect();
  const to = { left: btn.left + btn.width / 2 - 20, top: wrap.top + 2, width: 40, height: 40 };
  icon.style.visibility = 'hidden';
  flyDisc(from, to, from, () => { icon.style.visibility = ''; settle(icon); });
}
/**
 * Show one page immediately (no transition) and refresh what it needs.
 * @param {string} view Page id: overview | studio | review | queue | custom
 */
function showView(view) {
  $$('.view').forEach(v => v.classList.toggle('on', v.id === 'view-' + view));
  $$('.dock-btn[data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === view));
  $('#btnCustom').classList.toggle('on', view === 'custom');
  $('#pageName').textContent = pageNames[view];
  $('#app').classList.toggle('view-hide-course', view === 'queue' || view === 'custom');
  currentView = view;
  updateMini();
  if (view === 'overview') animateRings($('#view-overview'));
  if (view === 'queue') {
    animateRings($('#view-queue'));
    if (!activeCourseCode && currentCoursesList.length) viewCourseDetail(currentCoursesList[0].code);
  }
  if (view === 'studio') requestAnimationFrame(sizeCanvases);
  requestAnimationFrame(refreshThumbs);
}
$$('.dock-btn[data-view]').forEach(b => b.addEventListener('click', () => go(b.dataset.view)));
$('#brandHome').addEventListener('click', () => go('overview'));
$('#btnCustom').addEventListener('click', () => go('custom'));
$('#dockAvatar').addEventListener('click', () => go('custom'));

/**
 * Open a study "tab" by its older name (used by the plan, resume card, memory card and quiz results).
 * @param {string} tab today | reader | audio | quiz | mistakes | flashcards | reports | tutor
 */
function switchStudyTab(tab) {
  if (tab === 'today') { go('overview'); return; }
  if (tab === 'mistakes') { go('review'); setChoice('reviewTab', 'mistakes', false); return; }
  if (currentView !== 'studio') go('studio');
  setChoice('studioPane', 'study', false);
  if (tab === 'audio') {
    const ps = $('#paneStudy');
    if (ps.classList.contains('side-collapsed') && $('#playerCard').parentElement === $('#studySide')) $(':scope > .col-resizer .col-toggle', ps).click();
    requestAnimationFrame(() => $('#playerCard').scrollIntoView({ behavior: lowMotion() ? 'auto' : 'smooth', block: 'center' }));
    return;
  }
  const map = { reader: 'notes', quiz: 'quiz', flashcards: 'flash', reports: 'report', tutor: 'tutor' };
  selectTool(map[tab] || 'notes');
}

/** Go back to the overview and close every dialog (the title link). */
function goHome() {
  visibleOverlays().forEach(el => { el.style.display = 'none'; });
  go('overview');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ---------- Progress rings fill on entry, then stay still ---------- */
/**
 * Fill the progress rings in a page from zero to their value (then they stay still).
 * @param {ParentNode} scope Where the rings are
 */
function animateRings(scope) {
  $$('.ring, .big-ring', scope).forEach(r => {
    const c = $('.fg', r), rad = +c.getAttribute('r'), len = 2 * Math.PI * rad;
    c.style.strokeDasharray = len; c.style.strokeDashoffset = len;
    requestAnimationFrame(() => requestAnimationFrame(() => { c.style.strokeDashoffset = len * (1 - (+r.dataset.p) / 100); }));
  });
}

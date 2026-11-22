/**
 * Gemini Notebook 學習工作室 — shell page navigation and flying-record transitions.
 * Loaded immediately after studio-shell.js (relies on $, $$, player, skin, lowMotion, setChoice, moveDockTo, sizeCanvases, animateRings).
 */

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
const pageNames = { overview: '研讀總覽', studio: '研讀工作室', review: '弱點複習', literature: '文獻收集', queue: '批次排程', custom: '設計與自訂' };
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
  $('#app').classList.toggle('view-hide-course', view === 'literature');
  currentView = view;
  updateMini();
  if (view === 'overview') animateRings($('#view-overview'));
  if (view === 'literature' && window.loadLiteratureView) window.loadLiteratureView();
  if (view === 'queue') {
    animateRings($('#view-queue'));
    if (!activeCourseCode && currentCoursesList.length) viewCourseDetail(currentCoursesList[0].code);
  }
  if (view === 'studio') requestAnimationFrame(sizeCanvases);
  requestAnimationFrame(refreshThumbs);
}

// Close open .more-menu popovers when clicking outside or choosing a menu action.
document.addEventListener('click', e => {
  document.querySelectorAll('details.more-menu[open]').forEach(menu => {
    if (!menu.contains(e.target) || e.target.closest('.menu button, .menu a')) {
      menu.removeAttribute('open');
    }
  });
});

/** Render the pin toggle chips inside User Settings (#view-custom). */
function renderCustomPinChips() {
  const host = document.getElementById('customPinChips');
  if (!host || typeof order === 'undefined' || typeof BENCH === 'undefined') return;
  host.innerHTML = order.map(id => {
    const t = BENCH.find(x => x.id === id);
    if (!t) return '';
    const on = pinnedIds.includes(id);
    return `<button type="button" class="custom-pin-chip${on ? ' on' : ''}" data-pin-opt="${id}" aria-pressed="${on}"><i class="icon-pin"></i><span>${t.name}</span></button>`;
  }).join('');
}

document.addEventListener('click', e => {
  const opt = e.target.closest('[data-pin-opt]');
  if (!opt || typeof pinnedIds === 'undefined') return;
  const id = opt.dataset.pinOpt;
  pinnedIds = pinnedIds.includes(id) ? pinnedIds.filter(x => x !== id) : [...pinnedIds, id];
  if (typeof renderPins === 'function') renderPins();
});

/* Gemini Notebook 學習工作室 — 設計與自訂 controls (palettes, switches, avatar), keyboard and touch, focus mode,
   resizable columns, one-click reset, and the page start-up (preferences first, then the data).
   Loaded last of the classic scripts. */

/* ---------- Palettes ---------- */
const PALETTES = [
  { id: 'forest', name: '森林茶白', note: '暖紙底與森林綠，久讀不累', c: ['#f4eee6', '#1f4d3a', '#3f8f6b', '#15201a'] },
  { id: 'sage', name: '霧灰鼠尾草', note: '冷靜的灰綠，適合長時間專注', c: ['#eef2ef', '#354f52', '#52796f', '#172020'] },
  { id: 'espresso', name: '濃縮醇乳', note: '咖啡與奶油色，溫暖沉穩', c: ['#f5efe8', '#5c3d2e', '#8b5a3e', '#1e1814'] },
  { id: 'clay', name: '陶土赤陶', note: '柔和的赤陶，多一點活力', c: ['#f6efe9', '#9d4c36', '#c4664b', '#1d1715'] },
  { id: 'indigo', name: '靛藍晨霧', note: '低彩度藍，清爽而不刺眼', c: ['#f0f1f5', '#2f4a7a', '#4f6fa8', '#161a28'] },
];
/* Custom palettes: the user picks background, primary and accent; light and dark tokens are derived */
/**
 * The user's own palettes as stored in preferences.
 * @returns {Array<object>} Palettes {id, name, bg, primary, accent}
 */
function readCustomPalettes() {
  try { return JSON.parse(load('customPalettes', '[]')); } catch (e) { return []; }
}
let customPalettes = readCustomPalettes();
/**
 * CSS color-mix() of two colours.
 * @param {string} a First colour
 * @param {string} b Second colour
 * @param {number} pct Percent of the first colour
 * @returns {string} CSS colour
 */
const mix = (a, b, pct) => `color-mix(in srgb, ${a} ${pct}%, ${b})`;
/**
 * CSS tokens for one custom palette (a light and a derived dark set).
 * @param {{id: string, bg: string, primary: string, accent: string}} p Palette
 * @returns {string} CSS rules
 */
function paletteCSS(p) {
  return `html[data-palette="${p.id}"][data-mode="light"]{--canvas:${p.bg};--surface:#fff;--surface-2:${mix(p.bg, '#fff', 55)};--line:rgba(0,0,0,.09);--ink:#1f2421;--muted:#5d6460;--faint:#646b67;--primary:${p.primary};--primary-ink:#fff;--accent:${p.accent};--accent-soft:${mix(p.accent, '#fff', 14)};--accent-glow:${mix(p.accent, 'transparent', 30)};--dock-bg:${mix(p.primary, '#111', 35)};--track:${mix(p.bg, '#000', 92)};--thumb:#fff;--warn:#9a6a2c;--shadow:0 1px 2px rgba(0,0,0,.04),0 12px 32px rgba(0,0,0,.06)}
html[data-palette="${p.id}"][data-mode="dark"]{--canvas:${mix(p.primary, '#0d0f0e', 16)};--surface:${mix(p.primary, '#15181a', 20)};--surface-2:${mix(p.primary, '#1b1f21', 24)};--line:rgba(255,255,255,.1);--ink:#eceeed;--muted:#a8b0ab;--faint:#8a918d;--primary:${mix(p.accent, '#fff', 70)};--primary-ink:#101312;--accent:${mix(p.accent, '#fff', 78)};--accent-soft:${mix(p.accent, '#15181a', 22)};--accent-glow:${mix(p.accent, 'transparent', 30)};--dock-bg:${mix(p.primary, '#070808', 20)};--track:${mix(p.primary, '#1f2322', 18)};--thumb:${mix(p.primary, '#2b3030', 25)};--warn:#e0a560;--shadow:0 1px 2px rgba(0,0,0,.3),0 16px 40px rgba(0,0,0,.35)}`;
}
const customCSS = document.createElement('style'); document.head.append(customCSS);
const pc = $('#paletteCards'); pc.dataset.opt = 'palette';
const swatchHTML = c => `<span class="swatch">${c.map(x => `<i style="background:${x}"></i>`).join('')}</span>`;
/** Draw built-in and custom palette cards plus the add card. */
function renderPalettes() {
  customCSS.textContent = customPalettes.map(paletteCSS).join('\n');
  pc.innerHTML = PALETTES.map(p => `<button class="opt-card" data-value="${p.id}">${swatchHTML(p.c)}<b>${p.name}</b><span>${p.note}</span></button>`).join('')
    + customPalettes.map(p => `<div class="opt-card" role="button" tabindex="0" data-value="${p.id}">${swatchHTML([p.bg, p.primary, p.accent])}<b>${p.name}</b><span>自訂配色</span><button class="pal-del" data-del="${p.id}">刪除</button></div>`).join('')
    + `<button class="opt-card add-card" data-add><b>新增配色</b><span>選背景、主色與強調色</span></button>`;
  $$('.opt-card', pc).forEach(c => c.classList.toggle('on', c.dataset.value === root.dataset.palette));
  save('customPalettes', JSON.stringify(customPalettes));
}
pc.addEventListener('click', e => {
  const del = e.target.closest('[data-del]');
  if (del) {
    customPalettes = customPalettes.filter(p => p.id !== del.dataset.del);
    if (root.dataset.palette === del.dataset.del) setChoice('palette', 'forest');
    renderPalettes(); notify('已刪除自訂配色'); return;
  }
  if (e.target.closest('[data-add]')) { updatePalPreview(); $('#paletteDialog').showModal(); return; }
  const c = e.target.closest('.opt-card'); if (c) setChoice('palette', c.dataset.value);
});
pc.addEventListener('keydown', e => { const c = e.target.closest('div.opt-card'); if (c && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setChoice('palette', c.dataset.value); } });
/**
 * Show the colours being picked in the new-palette dialog preview.
 */
function updatePalPreview() {
  const pv = $('#palPreview');
  pv.style.background = $('#palBg').value;
  pv.style.setProperty('--pp-primary', $('#palPrimary').value);
  pv.style.setProperty('--pp-accent', $('#palAccent').value);
}
['#palBg', '#palPrimary', '#palAccent'].forEach(s => $(s).addEventListener('input', updatePalPreview));
$('#palSave').addEventListener('click', () => {
  const p = { id: 'c' + Date.now().toString(36), name: $('#palName').value.trim() || `自訂配色 ${customPalettes.length + 1}`, bg: $('#palBg').value, primary: $('#palPrimary').value, accent: $('#palAccent').value };
  customPalettes.push(p); renderPalettes(); setChoice('palette', p.id);
  $('#palName').value = ''; $('#paletteDialog').close(); notify(`已新增「${p.name}」`);
});
renderPalettes();

/* ---------- Switches ---------- */
const SWITCHES = [];
const SWITCH_SYNC = [];
/**
 * Wire a switch to a remembered preference and apply it now.
 * @param {string} id Switch selector
 * @param {string} key Preference name
 * @param {function(boolean): void} apply Applies the on / off state
 * @param {string} def Default ('true' or 'false')
 */
function bindSwitch(id, key, apply, def) {
  const sw = $(id); const v = load(key, def) === 'true';
  sw.setAttribute('aria-checked', v); apply(v);
  sw.addEventListener('click', () => { const nv = sw.getAttribute('aria-checked') !== 'true'; sw.setAttribute('aria-checked', nv); save(key, nv); apply(nv); });
  SWITCHES.push(() => { sw.setAttribute('aria-checked', def); apply(def === 'true'); });
  SWITCH_SYNC.push(() => { const nv = load(key, def) === 'true'; sw.setAttribute('aria-checked', nv); apply(nv); });
}
bindSwitch('#swMotion', 'motion', v => { root.dataset.motion = v ? 'full' : 'reduced'; }, 'true');
bindSwitch('#swFlip', 'flip', v => { flipOn = v; $('#visual').title = v ? '點一下切換視覺' : ''; $('#flipHint').textContent = v ? '點唱盤切換視覺' : '視覺可在「設計與自訂」切換'; }, 'true');
bindSwitch('#swHorizon', 'horizon', v => { $('#deck').classList.toggle('with-horizon', v); sizeCanvases(); }, 'false');
bindSwitch('#swFocusOpen', 'focusOpen', () => {}, 'false');
bindSwitch('#swGlass', 'glass', v => { root.dataset.glass = v ? 'on' : 'off'; }, 'false');
bindSwitch('#swPomoAuto', 'pomo.auto', () => {}, 'false');

/* ---------- Avatar: photo, initials, presets ---------- */
/**
 * Render the avatar everywhere from a {type, value} description and remember it.
 * @param {{type: string, value: string}} a Avatar: type text | icon | img
 * @param {boolean} persist Remember it (false while applying remembered preferences)
 */
function applyAvatar(a, persist = true) {
  const html = a.type === 'img' ? `<img src="${a.value}" alt="">` : a.type === 'icon' ? `<i class="icon-${a.value}"></i>` : `<span>${a.value || 'G'}</span>`;
  ['#dockAvatar', '#avatarPreview'].forEach(s => { $(s).innerHTML = html; });
  $('#dockName').textContent = (a.type === 'text' && a.value ? a.value : '我') + ' 的學習';
  $$('#presets button').forEach(b => b.classList.toggle('on', a.type === 'icon' && b.dataset.icon === a.value));
  if (persist) save('avatar', JSON.stringify(a));
}
/**
 * Shrink a photo to at most 256 px (JPEG) so the remembered avatar stays small.
 * @param {string} dataUrl Picked image as a data URL
 * @returns {Promise<string>} Smaller JPEG data URL
 */
function shrinkAvatar(dataUrl) {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, 256 / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      resolve(c.toDataURL('image/jpeg', 0.85));
    };
    img.onerror = () => resolve(dataUrl);
    img.src = dataUrl;
  });
}
$('#avatarFile').addEventListener('change', e => {
  const f = e.target.files[0]; if (!f) return;
  const r = new FileReader();
  r.onload = async () => applyAvatar({ type: 'img', value: await shrinkAvatar(r.result) });
  r.readAsDataURL(f);
});
$('#avatarInitials').addEventListener('input', e => applyAvatar({ type: 'text', value: e.target.value.trim().toUpperCase().slice(0, 3) }));
$('#presets').addEventListener('click', e => { const b = e.target.closest('button'); if (b) applyAvatar({ type: 'icon', value: b.dataset.icon }); });

/* ---------- Keyboard ---------- */
const typing = el => el.closest('input, textarea, select, [contenteditable="true"]');
document.addEventListener('keydown', ev => {
  // key events can target the document itself; treat that as the page body
  const e = { key: ev.key, altKey: ev.altKey, metaKey: ev.metaKey, ctrlKey: ev.ctrlKey, preventDefault: () => ev.preventDefault(), target: ev.target instanceof Element ? ev.target : document.body };
  // arrow keys inside a segmented control move the choice
  const seg = e.target.closest('.seg');
  if (seg && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
    const bs = $$('button', seg), i = bs.indexOf(e.target.closest('button')), d = ['ArrowLeft', 'ArrowUp'].includes(e.key) ? -1 : 1;
    const nb = bs[(i + d + bs.length) % bs.length]; if (nb) { e.preventDefault(); nb.click(); nb.focus(); }
    return;
  }
  // Alt + arrows on a block handle moves the block (up/down within a column, left/right between columns)
  const grip = e.target.closest('.blk-grip');
  if (grip && e.altKey && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
    e.preventDefault();
    const blk = grip.closest('.blk'), col = blk.parentElement, sibs = $$(':scope > .blk', col), i = sibs.indexOf(blk);
    if (e.key === 'ArrowUp' && i > 0) moveBlock(blk.id, col.id === 'studySide', sibs[i - 1].id);
    if (e.key === 'ArrowDown' && i < sibs.length - 1) moveBlock(blk.id, col.id === 'studySide', sibs[i + 2] ? sibs[i + 2].id : null);
    if (e.key === 'ArrowRight' && col.id === 'studyMain' && $('#paneStudy').dataset.layout !== 'stack') moveBlock(blk.id, true, null);
    if (e.key === 'ArrowLeft' && col.id === 'studySide') moveBlock(blk.id, false, null);
    requestAnimationFrame(() => $(`#${blk.id} > .blk-grip`).focus());
    announce('已移動區塊');
    return;
  }
  if (typing(e.target) || e.metaKey || e.ctrlKey || e.altKey || $('dialog[open]')) return;
  // player shortcuts: space play/pause, arrows ±15 s, , . speed
  if (e.key === ' ' && !e.target.closest('button, a, .tile, [role="button"]')) { e.preventDefault(); setPlaying(!player.playing); announce(player.playing ? '播放' : '暫停'); }
  else if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !e.target.closest('.tile, .col-resizer, .seg')) { seek(player.t + (e.key === 'ArrowLeft' ? -15 : 15)); }
  else if (e.key === ',' || e.key === '.') {
    const rates = ['0.75', '1', '1.25', '1.5', '2'], i = Math.max(0, rates.indexOf(String(player.speed)));
    const r = rates[Math.max(0, Math.min(rates.length - 1, i + (e.key === '.' ? 1 : -1)))];
    setChoice('speed', r); notify(`倍速 ${r}×`);
  }
});

/* ---------- Glass: drop the blur while scrolling ---------- */
let scrollTimer;
addEventListener('scroll', () => {
  if (root.dataset.glass !== 'on') return;
  root.classList.add('scrolling'); clearTimeout(scrollTimer);
  scrollTimer = setTimeout(() => root.classList.remove('scrolling'), 140);
}, { passive: true });

/* ---------- Touch: long-press to reorder tiles, drag a block by its handle ---------- */
(() => {
  let lift = null, timer = 0;
  /**
   * Finish a touch drag: drop the lifted look and every drop marker.
   */
  const end = () => { clearTimeout(timer); if (lift) { lift.el.classList.remove('lifted'); $$('.drop-target, .drop-before, .drop-end').forEach(x => x.classList.remove('drop-target', 'drop-before', 'drop-end')); } lift = null; };
  document.addEventListener('pointerdown', e => {
    if (e.pointerType === 'mouse') return;
    const tile = e.target.closest('#benchTiles .tile'), grip = e.target.closest('.blk-grip');
    if (!tile && !grip) return;
    const start = { x: e.clientX, y: e.clientY };
    /**
     * Lift the tile or block under the finger (after a long press on a tile, at once on a block handle).
     */
    const begin = () => {
      lift = { el: tile || grip.closest('.blk'), kind: tile ? 'tile' : 'blk', start };
      lift.el.classList.add('lifted'); navigator.vibrate?.(10);
    };
    if (grip) begin(); else timer = setTimeout(begin, 300);
    const move = ev => {
      if (!lift) { if (Math.hypot(ev.clientX - start.x, ev.clientY - start.y) > 8) clearTimeout(timer); return; }
      $$('.drop-target, .drop-before, .drop-end').forEach(x => x.classList.remove('drop-target', 'drop-before', 'drop-end'));
      const under = document.elementFromPoint(ev.clientX, ev.clientY);
      if (lift.kind === 'tile') { const t = under?.closest('#benchTiles .tile'); if (t && t !== lift.el) t.classList.add('drop-target'); lift.target = t; }
      else {
        const col = under?.closest('#studyMain, #studySide'); lift.col = col;
        if (col) { dragBlk = lift.el.id; const before = blockBefore(col, ev.clientY); lift.before = before; if (before) before.classList.add('drop-before'); else col.classList.add('drop-end'); }
      }
    };
    /**
     * Finger lifted: move the tile or block to where it was dropped and clean up the listeners.
     */
    const up = () => {
      document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', up); document.removeEventListener('pointercancel', up);
      if (lift?.kind === 'tile' && lift.target) moveTool(lift.el.dataset.tool, order.indexOf(lift.target.dataset.tool));
      if (lift?.kind === 'blk' && lift.col) { moveBlock(lift.el.id, lift.col.id === 'studySide', lift.before && lift.before.id); notify('已移動區塊'); }
      dragBlk = null; end();
    };
    document.addEventListener('pointermove', move); document.addEventListener('pointerup', up); document.addEventListener('pointercancel', up);
  });
  // while something is lifted, the finger drags it instead of scrolling the page
  document.addEventListener('touchmove', e => { if (lift) e.preventDefault(); }, { passive: false });
})();


/* ---------- Dialogs, usage guide, focus mode ---------- */
$$('dialog').forEach(d => {
  $$('[data-close]', d).forEach(b => b.addEventListener('click', () => d.close()));
  d.addEventListener('click', e => { if (e.target === d) d.close(); });
});
$('#btnHelp').addEventListener('click', () => openUsageModal());
/**
 * Enter or leave focus mode: full screen with the Dock and status hidden.
 * @param {boolean} on True to enter
 */
function setFocus(on) {
  $('#app').classList.toggle('focus', on);
  root.style.setProperty('--dock-w-root', on ? '0px' : ($('#app').classList.contains('dock-x') && innerWidth > 640 ? '216px' : '76px'));
  if (on && document.fullscreenElement == null && root.requestFullscreen) root.requestFullscreen().catch(() => {});
  if (!on && document.fullscreenElement) document.exitFullscreen().catch(() => {});
  requestAnimationFrame(refreshThumbs);
}
$('#btnFocus').addEventListener('click', () => setFocus(true));
$('#focusExit').addEventListener('click', () => setFocus(false));
// leaving full screen with Esc also leaves focus mode
document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && $('#app').classList.contains('focus')) setFocus(false); });

/* ---------- Resizable columns (per layout), collapse, restore ---------- */
/** Key used to remember width / collapse for a resizable area (study uses one per layout). */
const colKey = el => el.dataset.colKey === 'study' ? el.dataset.layout : el.dataset.colKey;
/**
 * Apply the remembered width and collapse state to one resizable area.
 * @param {HTMLElement} el Resizable area
 */
function applyColumns(el) {
  const k = colKey(el);
  if (!(k in COL_DEFAULTS)) { el.classList.remove('side-collapsed'); return; }
  el.style.setProperty('--side-pct', (+load('col.' + k, COL_DEFAULTS[k])) + '%');
  const collapsed = load('collapse.' + k, 'false') === 'true';
  el.classList.toggle('side-collapsed', collapsed);
  const tg = $(':scope > .col-resizer .col-toggle', el);
  const withPlayer = el.id === 'paneStudy' && $('#playerCard').parentElement === $('#studySide');
  const name = el.id === 'paneStudy' ? (withPlayer ? '播放器' : '右欄') : (COL_LABELS[k] || '右欄');
  const label = collapsed ? `展開${name}` : '收合右欄';
  tg.setAttribute('aria-label', label); tg.title = label;
  tg.innerHTML = collapsed ? '<i class="icon-panel-right-open"></i>' : '<i class="icon-panel-right-close"></i>';
}
$$('.resizable').forEach(el => {
  if (!$(':scope > .col-resizer', el)) {
    const first = el.firstElementChild;
    first.insertAdjacentHTML('afterend', '<div class="col-resizer" role="separator" aria-orientation="vertical" aria-label="拖曳調整欄寬，按兩下還原" tabindex="0"><button class="col-toggle" aria-label="收合右欄"><i class="icon-panel-right-close"></i></button></div>');
    $(':scope > .col-resizer', el).nextElementSibling.classList.add('side-col');
  }
});
$$('.resizable').forEach(el => {
  const rz = $(':scope > .col-resizer', el);
  const setPct = pct => {
    const k = colKey(el), w = el.getBoundingClientRect().width || 1000;
    const cs = getComputedStyle(el), sideMin = parseFloat(cs.getPropertyValue('--side-min')) || 320, mainMin = parseFloat(cs.getPropertyValue('--main-min')) || 420;
    pct = Math.max(sideMin / w * 100, Math.min((w - mainMin - 32) / w * 100, pct));
    el.style.setProperty('--side-pct', pct.toFixed(1) + '%'); save('col.' + k, Math.round(pct));
  };
  rz.addEventListener('pointerdown', e => {
    if (e.target.closest('.col-toggle') || el.classList.contains('side-collapsed')) return;
    rz.setPointerCapture(e.pointerId); rz.classList.add('dragging'); el.classList.add('cols-dragging');
    const move = ev => { const r = el.getBoundingClientRect(); setPct((r.right - ev.clientX) / r.width * 100); requestAnimationFrame(refreshThumbs); };
    /**
     * Finger lifted: move the tile or block to where it was dropped and clean up the listeners.
     */
    const up = () => { rz.classList.remove('dragging'); el.classList.remove('cols-dragging'); rz.removeEventListener('pointermove', move); rz.removeEventListener('pointerup', up); sizeCanvases(); };
    rz.addEventListener('pointermove', move); rz.addEventListener('pointerup', up);
  });
  rz.addEventListener('dblclick', () => { forget('col.' + colKey(el)); applyColumns(el); sizeCanvases(); notify('欄寬已還原'); });
  rz.addEventListener('keydown', e => { const d = { ArrowLeft: 2, ArrowRight: -2 }[e.key]; if (!d) return; e.preventDefault(); setPct(parseFloat(el.style.getPropertyValue('--side-pct')) + d); });
  $('.col-toggle', rz).addEventListener('click', () => {
    const k = colKey(el); save('collapse.' + k, !el.classList.contains('side-collapsed')); applyColumns(el); updateMini(); updateFab();
    requestAnimationFrame(() => { refreshThumbs(); sizeCanvases(); });
  });
  applyColumns(el);
});

$('#btnReset').addEventListener('click', () => $('#resetDialog').showModal());
$('#resetGo').addEventListener('click', () => {
  const keep = ['customPalettes', 'course'];
  // the server keeps only these keys; memory and the browser cache follow
  prefQueue = {};
  fetch('/api/preferences/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ keep }) }).catch(() => {});
  Object.keys(mem).filter(k => !keep.includes(k)).forEach(k => delete mem[k]);
  try { Object.keys(localStorage).filter(k => k.startsWith('v05.') && !keep.includes(k.slice(4))).forEach(k => localStorage.removeItem(k)); } catch (e) {}
  Object.entries(DEFAULTS).forEach(([k, v]) => setChoice(k, v, false));
  pinnedIds = [...DEFAULT_PINS]; order = [...DEFAULT_ORDER]; applyOrder(false);
  SWITCHES.forEach(f => f());
  setDockX(false, false);
  applyAvatar({ type: 'text', value: 'LK' }); $('#avatarInitials').value = 'LK';
  $$('.resizable').forEach(applyColumns); updateMini(); renderPalettes(); renderGreeting(); applyFontChoices(); applyTodayChoices();
  $('#resetDialog').close(); notify('已恢復預設設計');
});

/* ---------- Init: preferences first, then the data ---------- */
const q = new URLSearchParams(location.search);
if (q.get('still')) root.dataset.motion = 'reduced';
/**
 * Apply every remembered preference to the page: palette, mode, style, layout, order, pins, switches,
 * avatar, Dock width, column widths and today's choices. Runs once from the browser cache (first paint)
 * and again when the preferences recorded on this computer arrive.
 */
function applyAllPreferences() {
  prefMute = true;
  customPalettes = readCustomPalettes(); renderPalettes();
  setChoice('palette', load('palette', 'forest'), false);
  setChoice('mode', load('mode', 'auto'), false);
  setChoice('style', load('style', 'flow'), false);
  setChoice('arr', load('arr', 'matrix'), false);
  setChoice('pace', load('pace', 'relax'), false);
  setChoice('speed', load('speed', '1'), false);
  setChoice('skin', load('skin', 'vinyl'), false);
  let avatar;
  try { avatar = JSON.parse(load('avatar', '{"type":"text","value":"LK"}')); } catch (e) { avatar = { type: 'text', value: 'LK' }; }
  applyAvatar(avatar, false);
  if (avatar.type === 'text') $('#avatarInitials').value = avatar.value;
  SWITCH_SYNC.forEach(f => f());
  pinnedIds = readPins(); order = readOrder();
  setChoice('layout', load('layout', 'stage'), false);
  applyOrder(false);
  setDockX(load('dockX', 'false') === 'true', false);
  $$('.resizable').forEach(applyColumns);
  setChoice('pomoStyle', load('pomoStyle', 'ring'), false);
  applyTodayChoices();
  applyFocusHabits();
  if (typeof applyFontChoices === 'function') applyFontChoices();
  renderGreeting();
  prefMute = false;
}
applyAllPreferences();
setTrack(null);
renderContinue();
document.fonts && document.fonts.ready.then(() => { refreshThumbs(); sizeCanvases(); });
window.addEventListener('resize', () => sizeCanvases());

/* Data: status and quota refresh on their own; the course page refreshes every 15 seconds while open.
   Started on DOMContentLoaded so the add-ons in studio-learning.js are already wired in. */
document.addEventListener('DOMContentLoaded', async () => {
  $('#studyCourseSelect').addEventListener('change', onStudyCourseSelected);
  fetchStatus(); fetchQuota();
  setInterval(fetchStatus, 5000);
  setInterval(fetchQuota, 60000);
  setInterval(() => {
    if (currentView === 'queue' && activeCourseCode && $('#courseDetailSection').style.display !== 'none') viewCourseDetail(activeCourseCode, true);
  }, 15000);
  try {
    if (await syncPreferences()) applyAllPreferences();
    loadFonts();
    restorePomo();
    await fetchCourses();
    await initStudyPortal();
  } finally {
    $('#app').classList.remove('loading');
    animateRings($('#view-overview'));
    requestAnimationFrame(() => { refreshThumbs(); sizeCanvases(); renderMiniDiscs(); });
  }
  /* Shortcuts for checking a page: ?view=studio&tool=quiz&pane=courses&review=cards */
  if (q.get('view')) go(q.get('view'));
  if (q.get('pane')) setChoice('studioPane', q.get('pane'), false);
  if (q.get('tool')) selectTool(q.get('tool'));
  if (q.get('review')) setChoice('reviewTab', q.get('review'), false);
  if (load('focusOpen', 'false') === 'true') setFocus(true);
});

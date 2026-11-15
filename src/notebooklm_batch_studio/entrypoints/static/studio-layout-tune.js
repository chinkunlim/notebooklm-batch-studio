/**
 * Gemini Notebook 學習工作室 — WYSIWYG Layout Tune Mode.
 * Lets users directly drag-resize panel widths and heights per viewport (desktop / tablet / mobile),
 * snaps to the 8pt grid, persists locally, and copies a clean diff spec for developers/agents.
 */

let _tuneActive = false;
let _tuneDragState = null;

/**
 * Determine current responsive viewport bucket ('desktop', 'tablet', or 'mobile').
 * @returns {string} Viewport category
 */
function guideViewportBucket() {
  const w = window.innerWidth;
  if (w <= 680) return 'mobile';
  if (w <= 1023) return 'tablet';
  return 'desktop';
}

/**
 * Build a full ancestor breadcrumb path with viewport and box dimensions for unambiguous locating.
 * @param {Element} el Target DOM element
 * @returns {string} Full breadcrumb selector path
 */
function guideFullPathFor(el) {
  const labelFn = typeof guideLabelFor === 'function' ? guideLabelFor : node => node.tagName.toLowerCase();
  const parts = [labelFn(el)];
  let cur = el.parentElement;
  let hops = 0;
  while (cur && cur.id !== 'app' && cur.tagName !== 'BODY' && hops < 4) {
    const hasMeaningful = cur.id || (typeof cur.className === 'string' && cur.className.trim());
    if (hasMeaningful) {
      parts.unshift(labelFn(cur));
      hops += 1;
    }
    cur = cur.parentElement;
  }
  const r = el.getBoundingClientRect();
  return `[${guideViewportBucket()} ${window.innerWidth}px] ${parts.join(' > ')} (${Math.round(r.width)}x${Math.round(r.height)})`;
}

/**
 * Return the localStorage key for layout overrides scoped to the current viewport bucket.
 * @returns {string} Storage key
 */
function _tuneStorageKey() {
  const vp = typeof guideViewportBucket === 'function' ? guideViewportBucket() : 'desktop';
  return `v05.layoutTune.${vp}`;
}

/**
 * Load saved layout overrides for the active viewport.
 * @returns {object} Map of selector path to { width, height }
 */
function _loadTuneMap() {
  try {
    return JSON.parse(localStorage.getItem(_tuneStorageKey()) || '{}');
  } catch {
    return {};
  }
}

/**
 * Persist layout overrides for the active viewport.
 * @param {object} map Map of selector path to { width, height }
 */
function _saveTuneMap(map) {
  try {
    localStorage.setItem(_tuneStorageKey(), JSON.stringify(map));
  } catch {
    // Ignore storage quota errors in private browsing.
  }
}

/**
 * Apply saved width/height overrides to matching visible elements for the current viewport.
 * @returns {void}
 */
function applySavedLayoutTunes() {
  const map = _loadTuneMap();
  Object.entries(map).forEach(([sel, dims]) => {
    const el = document.querySelector(sel);
    if (!el || !dims) return;
    if (dims.width) el.style.width = `${dims.width}px`;
    if (dims.height) el.style.minHeight = `${dims.height}px`;
  });
}

/**
 * Toggle interactive drag-to-resize handles on major layout cards and panels.
 * @returns {void}
 */
function toggleLayoutTuneMode() {
  _tuneActive = !_tuneActive;
  document.getElementById('btnTuneMode')?.classList.toggle('on', _tuneActive);
  document.querySelectorAll('.tune-box').forEach(el => el.classList.remove('tune-box'));
  document.querySelectorAll('.tune-handle, .tune-bar').forEach(el => el.remove());
  if (!_tuneActive) {
    showToast('已關閉版面拖曳微調模式', 'info', 1800);
    return;
  }
  _mountTuneHandles();
  _mountTuneActionBar();
  showToast('已開啟拖曳微調：拖拉面板右下角即可直接調整大小（自動吸附 8px 網格）', 'info', 3000);
}

/**
 * Attach drag-resize corner handles to visible tunable containers.
 * @returns {void}
 */
function _mountTuneHandles() {
  const targets = document.querySelectorAll('.card[id], #splitStage, #cramPanel, #paneCourses .card, #paneStudy .card');
  targets.forEach(el => {
    if (!el.id || !el.offsetParent) return;
    el.classList.add('tune-box');
    const handle = document.createElement('button');
    handle.type = 'button';
    handle.className = 'tune-handle';
    handle.title = '拖曳調整寬度與高度（8px 網格）';
    handle.setAttribute('aria-label', `調整 ${el.id} 尺寸`);
    handle.onpointerdown = e => _startTuneDrag(e, el);
    el.appendChild(handle);
  });
}

/**
 * Render floating action bar for copying diff spec or resetting tuned dimensions.
 * @returns {void}
 */
function _mountTuneActionBar() {
  const bar = document.createElement('div');
  bar.className = 'tune-bar';
  bar.innerHTML = `<span class="small">拖曳微調中（${typeof guideViewportBucket === 'function' ? guideViewportBucket() : 'desktop'}）</span>
    <button type="button" class="btn btn-soft btn-sm" onclick="copyLayoutTuneDiff()">複製微調規格</button>
    <button type="button" class="btn btn-ghost btn-sm" onclick="resetLayoutTunes()">還原預設</button>
    <button type="button" class="btn btn-primary btn-sm" onclick="toggleLayoutTuneMode()">完成</button>`;
  document.body.appendChild(bar);
}

/**
 * Begin pointer drag-resize on a target container, snapping to 8px increments.
 * @param {PointerEvent} e Pointer down event
 * @param {HTMLElement} el Target container
 */
function _startTuneDrag(e, el) {
  e.preventDefault();
  e.stopPropagation();
  const rect = el.getBoundingClientRect();
  _tuneDragState = { el, startX: e.clientX, startY: e.clientY, startW: rect.width, startH: rect.height };
  window.addEventListener('pointermove', _onTuneDragMove);
  window.addEventListener('pointerup', _endTuneDrag, { once: true });
}

/**
 * Snap pixel delta to 8px grid and apply live preview size during drag.
 * @param {PointerEvent} e Pointer move event
 */
function _onTuneDragMove(e) {
  if (!_tuneDragState) return;
  const { el, startX, startY, startW, startH } = _tuneDragState;
  const snap = v => Math.max(120, Math.round(v / 8) * 8);
  const nextW = snap(startW + (e.clientX - startX));
  const nextH = snap(startH + (e.clientY - startY));
  el.style.width = `${nextW}px`;
  el.style.minHeight = `${nextH}px`;
}

/**
 * Persist adjusted dimensions when pointer drag completes.
 * @returns {void}
 */
function _endTuneDrag() {
  window.removeEventListener('pointermove', _onTuneDragMove);
  if (!_tuneDragState) return;
  const { el } = _tuneDragState;
  const r = el.getBoundingClientRect();
  const map = _loadTuneMap();
  map[`#${el.id}`] = { width: Math.round(r.width), height: Math.round(r.height) };
  _saveTuneMap(map);
  _tuneDragState = null;
  if (typeof renderLayoutGuides === 'function') renderLayoutGuides();
}

/**
 * Copy a structured summary of tuned layout changes to the clipboard for Agent/CSS sync.
 * @returns {void}
 */
function copyLayoutTuneDiff() {
  const vp = typeof guideViewportBucket === 'function' ? guideViewportBucket() : 'desktop';
  const map = _loadTuneMap();
  const entries = Object.entries(map);
  if (!entries.length) {
    showToast('目前尚未拖曳調整任何區塊尺寸', 'warning');
    return;
  }
  const text = `[Layout Tune @ ${vp} ${window.innerWidth}px]\n` +
    entries.map(([sel, d]) => `- ${sel}: width=${d.width}px, min-height=${d.height}px`).join('\n');
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).catch(() => {});
  showToast('已複製版面微調規格，可直接貼給 AI 套用', 'success', 2600);
}

/**
 * Clear saved layout tune overrides for the current viewport and restore default CSS sizing.
 * @returns {void}
 */
function resetLayoutTunes() {
  const map = _loadTuneMap();
  Object.keys(map).forEach(sel => {
    const el = document.querySelector(sel);
    if (el) {
      el.style.width = '';
      el.style.minHeight = '';
    }
  });
  localStorage.removeItem(_tuneStorageKey());
  if (typeof renderLayoutGuides === 'function') renderLayoutGuides();
  showToast('已還原目前裝置視口的預設版面尺寸', 'info', 2200);
}

window.addEventListener('resize', () => {
  applySavedLayoutTunes();
});
document.addEventListener('DOMContentLoaded', applySavedLayoutTunes);

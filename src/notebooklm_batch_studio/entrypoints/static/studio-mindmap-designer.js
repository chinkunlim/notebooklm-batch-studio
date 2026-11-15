/**
 * @file studio-mindmap-designer.js
 * @description Mind map toolbar controls and customizable style designer popover for the study workbench.
 */

/**
 * Send a control command to the embedded mind map iframe.
 * @param {string} cmd Command name (zoomOut, fit, zoomIn, expandAll, toggleOutline, applyStyle, exportSvg)
 * @param {HTMLElement} [btn] Optional button whose active state toggles
 * @param {*} [value] Optional command payload (such as style config object)
 */
function sendMindmapCmd(cmd, btn, value) {
  const frame = document.querySelector('#reportContentContainer iframe.report-frame');
  if (frame && frame.contentWindow) frame.contentWindow.postMessage({ type: 'mindmap-cmd', cmd, value }, '*');
  if (cmd === 'toggleOutline' && btn) btn.classList.toggle('on');
  if (cmd === 'expandAll' && btn) {
    const on = btn.classList.toggle('on');
    btn.textContent = on ? '收合節點' : '全部展開';
  }
}

const MM_DEFAULT_STYLE = {
  layout: 'tree-right',
  theme: 'forest',
  nodeShape: 'rounded',
  connector: 'curve',
  bg: 'dots',
  fontSize: 'md',
  density: 'normal',
};

/**
 * Load saved user mind map style from localStorage.
 * @returns {object} Mind map style configuration
 */
function loadMindmapStyle() {
  try {
    const s = JSON.parse(localStorage.getItem('nb_mindmap_style') || 'null');
    return s && typeof s === 'object' ? { ...MM_DEFAULT_STYLE, ...s } : { ...MM_DEFAULT_STYLE };
  } catch (e) { return { ...MM_DEFAULT_STYLE }; }
}

/**
 * Update a single mind map style option, persist it, and sync to the iframe.
 * @param {string} key Option key
 * @param {string} val Option value
 */
function setMindmapStyleOption(key, val) {
  const cfg = { ...loadMindmapStyle(), [key]: val };
  try { localStorage.setItem('nb_mindmap_style', JSON.stringify(cfg)); } catch (e) { /* ignore */ }
  sendMindmapCmd('applyStyle', null, cfg);
  const sel = document.getElementById('mmLayoutSel');
  if (sel) sel.value = cfg.layout;
  renderMindmapStylePop();
}

/**
 * Reset mind map style to defaults and re-render.
 */
function resetMindmapStyle() {
  try { localStorage.setItem('nb_mindmap_style', JSON.stringify(MM_DEFAULT_STYLE)); } catch (e) { /* ignore */ }
  sendMindmapCmd('applyStyle', null, { ...MM_DEFAULT_STYLE });
  const sel = document.getElementById('mmLayoutSel');
  if (sel) sel.value = MM_DEFAULT_STYLE.layout;
  renderMindmapStylePop();
}

/**
 * Build option pill buttons for one row inside the mind map style designer popover.
 * @param {string} key Style config key
 * @param {Array<[string, string, string?]>} items Array of [value, label, swatchColor]
 * @param {object} cfg Current style config
 * @returns {string} HTML string
 */
function mmStyleRowHtml(key, items, cfg) {
  return items.map(([v, label, swatch]) =>
    `<button type="button" class="reader-pill-btn${cfg[key] === v ? ' on' : ''}" onclick="setMindmapStyleOption('${key}','${v}')">${swatch ? `<span class="mm-swatch" style="background:${swatch}"></span>` : ''}${label}</button>`
  ).join('');
}

/**
 * Render the floating mind map style designer popover inside `#panelReports`.
 */
function renderMindmapStylePop() {
  const panel = document.getElementById('panelReports');
  if (!panel) return;
  let pop = document.getElementById('mmStylePop');
  if (!pop) {
    pop = document.createElement('div');
    pop.id = 'mmStylePop';
    pop.className = 'mm-style-pop';
    panel.appendChild(pop);
  }
  const cfg = loadMindmapStyle();
  pop.innerHTML = `
    <div class="mm-pop-row"><span>主題配色</span><div>${mmStyleRowHtml('theme', [['forest', '森林', '#1b4d3e'], ['dark', '夜讀', '#0f172a'], ['ocean', '海洋', '#0369a1'], ['warm', '暖陽', '#c2410c'], ['mono', '極簡', '#171717']], cfg)}</div></div>
    <div class="mm-pop-row"><span>節點形狀</span><div>${mmStyleRowHtml('nodeShape', [['rounded', '圓角'], ['pill', '膠囊'], ['sharp', '方框'], ['underline', '底線']], cfg)}</div></div>
    <div class="mm-pop-row"><span>連線樣式</span><div>${mmStyleRowHtml('connector', [['curve', '曲線'], ['elbow', '折線'], ['straight', '直線']], cfg)}</div></div>
    <div class="mm-pop-row"><span>畫布背景</span><div>${mmStyleRowHtml('bg', [['dots', '點陣'], ['grid', '方格'], ['solid', '純色']], cfg)}</div></div>
    <div class="mm-pop-row"><span>字級</span><div>${mmStyleRowHtml('fontSize', [['sm', '小'], ['md', '標準'], ['lg', '大']], cfg)}</div></div>
    <div class="mm-pop-row"><span>間距</span><div>${mmStyleRowHtml('density', [['compact', '緊湊'], ['normal', '標準'], ['relaxed', '寬鬆']], cfg)}</div></div>
    <div class="mm-pop-foot">
      <button type="button" class="reader-pill-btn" onclick="sendMindmapCmd('exportSvg')">下載 SVG</button>
      <button type="button" class="reader-pill-btn" onclick="resetMindmapStyle()">恢復預設</button>
    </div>`;
}

/**
 * Toggle the floating mind map style designer popover.
 * @param {Event} [ev] Click event
 */
function toggleMindmapStylePop(ev) {
  if (ev) ev.stopPropagation();
  renderMindmapStylePop();
  const pop = document.getElementById('mmStylePop');
  const btn = document.getElementById('mmStyleBtn');
  if (!pop) return;
  const open = pop.classList.toggle('open');
  if (btn) btn.classList.toggle('on', open);
}

document.addEventListener('click', e => {
  const pop = document.getElementById('mmStylePop');
  if (pop && pop.classList.contains('open') && !e.target.closest('#mmStylePop, #mmStyleBtn')) {
    pop.classList.remove('open');
    document.getElementById('mmStyleBtn')?.classList.remove('on');
  }
});

/**
 * Render mind map layout selector, zoom/outline buttons, and style designer toggle.
 * @param {HTMLElement} kindBox Left-hand toolbar container
 */
function renderMindmapTools(kindBox) {
  const cfg = loadMindmapStyle();
  kindBox.innerHTML = `
    <select id="mmLayoutSel" class="reader-pill-btn" aria-label="心智圖版型" onchange="setMindmapStyleOption('layout', this.value)">
      <option value="tree-right" ${cfg.layout === 'tree-right' ? 'selected' : ''}>橫向樹狀</option>
      <option value="tree-bilateral" ${cfg.layout === 'tree-bilateral' ? 'selected' : ''}>雙向放射</option>
      <option value="org-down" ${cfg.layout === 'org-down' ? 'selected' : ''}>由上而下</option>
    </select>
    <button type="button" class="icon-btn" onclick="sendMindmapCmd('zoomOut')" aria-label="縮小">－</button>
    <button type="button" class="reader-pill-btn" onclick="sendMindmapCmd('fit')">適應畫面</button>
    <button type="button" class="icon-btn" onclick="sendMindmapCmd('zoomIn')" aria-label="放大">＋</button>
    <button type="button" class="reader-pill-btn" onclick="sendMindmapCmd('expandAll', this)">全部展開</button>
    <button type="button" class="reader-pill-btn" id="mmOutlineBtn" onclick="sendMindmapCmd('toggleOutline', this)">大綱文字</button>
    <button type="button" class="reader-pill-btn" id="mmStyleBtn" onclick="toggleMindmapStylePop(event)">🎨 自訂樣式</button>`;
}

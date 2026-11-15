/**
 * @file studio-mindmap-designer.js
 * @description Mind map toolbar controls, presets, live preview, and customizable style designer.
 */

/**
 * Send a control command to the embedded mind map iframe.
 * @param {string} cmd Command name (zoomOut, fit, zoomIn, expandAll, toggleOutline, applyStyle, applyFont, exportSvg)
 * @param {HTMLElement} [btn] Optional button whose active state toggles
 * @param {*} [value] Optional command payload
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

const MM_PRESETS = [
  { id: 'forest-classic', label: '經典森林', cfg: { layout: 'tree-right', theme: 'forest', nodeShape: 'rounded', connector: 'curve', bg: 'dots', density: 'normal' } },
  { id: 'night-focus', label: '夜間專注', cfg: { layout: 'tree-bilateral', theme: 'dark', nodeShape: 'pill', connector: 'curve', bg: 'solid', density: 'normal' } },
  { id: 'ocean-deck', label: '海洋簡報', cfg: { layout: 'org-down', theme: 'ocean', nodeShape: 'rounded', connector: 'elbow', bg: 'grid', density: 'relaxed' } },
  { id: 'warm-notes', label: '暖陽筆記', cfg: { layout: 'tree-right', theme: 'warm', nodeShape: 'underline', connector: 'curve', bg: 'dots', density: 'normal' } },
  { id: 'exam-mono', label: '考前極簡', cfg: { layout: 'tree-right', theme: 'mono', nodeShape: 'sharp', connector: 'straight', bg: 'solid', density: 'compact' } },
];

const MM_PREVIEW_PALETTES = {
  forest: { bg: '#faf8f4', dot: '#e4dfd5', fill: '#ffffff', text: '#1f2421', pal: ['#1b4d3e', '#2e6f5b', '#b45309', '#2563eb'] },
  dark: { bg: '#0f172a', dot: '#334155', fill: '#1e293b', text: '#e2e8f0', pal: ['#0284c7', '#38bdf8', '#fbbf24', '#a78bfa'] },
  ocean: { bg: '#f0f7ff', dot: '#d4e4f7', fill: '#ffffff', text: '#0f172a', pal: ['#0369a1', '#0d9488', '#2563eb', '#4f46e5'] },
  warm: { bg: '#fdf8f3', dot: '#ecdcc9', fill: '#fffcf8', text: '#292018', pal: ['#9a3412', '#c2410c', '#b45309', '#0f766e'] },
  mono: { bg: '#fafafa', dot: '#e5e5e5', fill: '#ffffff', text: '#171717', pal: ['#171717', '#404040', '#525252', '#737373'] },
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
 * Persist and broadcast a complete mind map style configuration to all views.
 * @param {object} cfg Complete mind map style config
 */
function syncMindmapStyle(cfg) {
  try { localStorage.setItem('nb_mindmap_style', JSON.stringify(cfg)); } catch (e) { /* ignore */ }
  sendMindmapCmd('applyStyle', null, cfg);
  const sel = document.getElementById('mmLayoutSel');
  if (sel) sel.value = cfg.layout;
  renderMindmapStylePop();
  renderMindmapCustomCard();
}

/**
 * Update a single mind map style option, persist it, and sync to all views.
 * @param {string} key Option key
 * @param {string} val Option value
 */
function setMindmapStyleOption(key, val) {
  syncMindmapStyle({ ...loadMindmapStyle(), [key]: val });
}

/**
 * Apply a named mind map preset template.
 * @param {string} presetId Preset id from MM_PRESETS
 */
function applyMindmapPreset(presetId) {
  const found = MM_PRESETS.find(p => p.id === presetId);
  if (!found) return;
  syncMindmapStyle({ ...loadMindmapStyle(), ...found.cfg });
}

/**
 * Reset mind map style to defaults and re-render.
 */
function resetMindmapStyle() {
  syncMindmapStyle({ ...MM_DEFAULT_STYLE });
}

/**
 * Build option pill buttons for one row inside the mind map style designer.
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
 * Build the shared preset + style controls HTML used in both the popover and settings card.
 * @param {object} cfg Current mind map style configuration
 * @param {boolean} includeLayout Whether to include the layout selector row
 * @returns {string} HTML string
 */
function mmDesignerRowsHtml(cfg, includeLayout) {
  const presetBtns = MM_PRESETS.map(p => {
    const active = Object.entries(p.cfg).every(([k, v]) => cfg[k] === v);
    return `<button type="button" class="reader-pill-btn${active ? ' on' : ''}" onclick="applyMindmapPreset('${p.id}')">${p.label}</button>`;
  }).join('');
  const layoutRow = includeLayout
    ? `<div class="mm-pop-row"><span>版型</span><div>${mmStyleRowHtml('layout', [['tree-right', '橫向樹狀'], ['tree-bilateral', '雙向放射'], ['org-down', '由上而下']], cfg)}</div></div>`
    : '';
  return `
    <div class="mm-pop-row"><span>風格模板</span><div>${presetBtns}</div></div>
    ${layoutRow}
    <div class="mm-pop-row"><span>主題配色</span><div>${mmStyleRowHtml('theme', [['forest', '森林', '#1b4d3e'], ['dark', '夜讀', '#0f172a'], ['ocean', '海洋', '#0369a1'], ['warm', '暖陽', '#c2410c'], ['mono', '極簡', '#171717']], cfg)}</div></div>
    <div class="mm-pop-row"><span>節點形狀</span><div>${mmStyleRowHtml('nodeShape', [['rounded', '圓角'], ['pill', '膠囊'], ['sharp', '方框'], ['underline', '底線']], cfg)}</div></div>
    <div class="mm-pop-row"><span>連線樣式</span><div>${mmStyleRowHtml('connector', [['curve', '曲線'], ['elbow', '折線'], ['straight', '直線']], cfg)}</div></div>
    <div class="mm-pop-row"><span>畫布背景</span><div>${mmStyleRowHtml('bg', [['dots', '點陣'], ['grid', '方格'], ['solid', '純色']], cfg)}</div></div>
    <div class="mm-pop-row"><span>字級</span><div>${mmStyleRowHtml('fontSize', [['sm', '小'], ['md', '標準'], ['lg', '大']], cfg)}</div></div>
    <div class="mm-pop-row"><span>間距</span><div>${mmStyleRowHtml('density', [['compact', '緊湊'], ['normal', '標準'], ['relaxed', '寬鬆']], cfg)}</div></div>`;
}

/**
 * Build an SVG path string for one preview edge.
 * @param {object} cfg Mind map style configuration
 * @param {{x: number, y: number}} p1 Start point
 * @param {{x: number, y: number}} p2 End point
 * @param {boolean} vertical True for top-down layout
 * @returns {string} SVG path d attribute
 */
function mmPreviewEdgePath(cfg, p1, p2, vertical) {
  if (cfg.connector === 'straight') return `M${p1.x},${p1.y} L${p2.x},${p2.y}`;
  const m = vertical ? (p1.y + p2.y) / 2 : (p1.x + p2.x) / 2;
  if (cfg.connector === 'elbow') {
    return vertical
      ? `M${p1.x},${p1.y} L${p1.x},${m} L${p2.x},${m} L${p2.x},${p2.y}`
      : `M${p1.x},${p1.y} L${m},${p1.y} L${m},${p2.y} L${p2.x},${p2.y}`;
  }
  return vertical
    ? `M${p1.x},${p1.y} C${p1.x},${m} ${p2.x},${m} ${p2.x},${p2.y}`
    : `M${p1.x},${p1.y} C${m},${p1.y} ${m},${p2.y} ${p2.x},${p2.y}`;
}

/**
 * Return sample node coordinates for the preview SVG based on layout.
 * @param {string} layout Layout key
 * @param {string[]} pal Theme palette colors
 * @returns {Array<object>} Sample node descriptors
 */
function mmPreviewNodes(layout, pal) {
  if (layout === 'org-down') {
    return [
      { x: 120, y: 24, w: 92, t: '核心主題', c: pal[0], root: true },
      { x: 26, y: 124, w: 80, t: '理論架構', c: pal[1] },
      { x: 126, y: 124, w: 80, t: '實務應用', c: pal[2] },
      { x: 226, y: 124, w: 80, t: '考點整理', c: pal[3] },
    ];
  }
  if (layout === 'tree-bilateral') {
    return [
      { x: 122, y: 95, w: 88, t: '核心主題', c: pal[0], root: true },
      { x: 244, y: 54, w: 74, t: '重點 A', c: pal[1] },
      { x: 244, y: 136, w: 74, t: '重點 B', c: pal[2] },
      { x: 14, y: 95, w: 74, t: '延伸反思', c: pal[3], left: true },
    ];
  }
  return [
    { x: 20, y: 95, w: 92, t: '核心主題', c: pal[0], root: true },
    { x: 186, y: 38, w: 88, t: '一、理論架構', c: pal[1] },
    { x: 186, y: 95, w: 88, t: '二、臨床案例', c: pal[2] },
    { x: 186, y: 152, w: 88, t: '三、考題整理', c: pal[3] },
  ];
}

/**
 * Draw a miniature SVG preview of the current mind map style inside `#mmPreviewBox`.
 */
function renderMindmapPreview() {
  const box = document.getElementById('mmPreviewBox');
  if (!box) return;
  const cfg = loadMindmapStyle();
  const th = MM_PREVIEW_PALETTES[cfg.theme] || MM_PREVIEW_PALETTES.forest;
  box.style.backgroundColor = th.bg;
  box.style.backgroundImage = cfg.bg === 'grid'
    ? `linear-gradient(${th.dot} 1px, transparent 1px), linear-gradient(90deg, ${th.dot} 1px, transparent 1px)`
    : (cfg.bg === 'dots' ? `radial-gradient(${th.dot} 1px, transparent 1px)` : 'none');
  box.style.backgroundSize = cfg.bg === 'grid' ? '18px 18px' : '16px 16px';
  const rx = cfg.nodeShape === 'pill' ? 14 : (cfg.nodeShape === 'sharp' ? 2 : 8);
  const nodes = mmPreviewNodes(cfg.layout, th.pal);
  const root = nodes[0];
  const paths = nodes.slice(1).map(n => {
    const vert = cfg.layout === 'org-down';
    const p1 = vert ? { x: root.x + root.w / 2, y: root.y + 30 } : { x: n.left ? root.x : root.x + root.w, y: root.y + 15 };
    const p2 = vert ? { x: n.x + n.w / 2, y: n.y } : { x: n.left ? n.x + n.w : n.x, y: n.y + 15 };
    return `<path d="${mmPreviewEdgePath(cfg, p1, p2, vert)}" fill="none" stroke="${n.c}" stroke-width="2" stroke-opacity="0.65"/>`;
  }).join('');
  const fs = cfg.fontSize === 'lg' ? 12.5 : (cfg.fontSize === 'sm' ? 10.5 : 11.5);
  const shapes = nodes.map(n => {
    const boxHtml = cfg.nodeShape === 'underline' && !n.root
      ? `<line x1="${n.x + 2}" y1="${n.y + 27}" x2="${n.x + n.w - 2}" y2="${n.y + 27}" stroke="${n.c}" stroke-width="2"/>`
      : `<rect x="${n.x}" y="${n.y}" width="${n.w}" height="30" rx="${rx}" fill="${n.root ? n.c : th.fill}" stroke="${n.c}" stroke-width="${n.root ? 0 : 1.6}"/>`;
    return `${boxHtml}<text x="${n.x + n.w / 2}" y="${n.y + 19}" text-anchor="middle" font-size="${fs}" font-weight="600" fill="${n.root ? '#fff' : th.text}">${n.t}</text>`;
  }).join('');
  box.innerHTML = `<svg viewBox="0 0 332 210" xmlns="http://www.w3.org/2000/svg" style="font-family:var(--font-sans)">${paths}${shapes}</svg>`;
}

/**
 * Render the mind map preset & customizer controls inside `設計與自訂`.
 */
function renderMindmapCustomCard() {
  const host = document.getElementById('mmCustomControls');
  if (host) host.innerHTML = mmDesignerRowsHtml(loadMindmapStyle(), true);
  renderMindmapPreview();
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
  pop.innerHTML = `${mmDesignerRowsHtml(loadMindmapStyle(), false)}
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

renderMindmapCustomCard();

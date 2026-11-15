"""HTML/CSS/JS template constants for standalone interactive mind map rendering."""

from __future__ import annotations

_MINDMAP_HTML_CSS = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    height: 100%; overflow: hidden; background: #faf8f4; color: #1f2421;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang TC", "Noto Sans TC", sans-serif;
  }
  .bar {
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px; padding: 10px 14px; background: #ffffff; border-bottom: 1px solid #e7e2d8;
  }
  .bar-title {
    font-size: 13px; font-weight: 600; color: #4b5550;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .tools { display: flex; align-items: center; gap: 6px; flex: none; }
  .btn {
    border: 1px solid #dfd9ce; background: #faf8f4; color: #1f2421;
    border-radius: 999px; padding: 5px 11px; font-size: 12px; cursor: pointer; font-weight: 500;
  }
  .btn:hover { border-color: #1b4d3e; color: #1b4d3e; }
  .btn.on { background: #1b4d3e; color: #ffffff; border-color: #1b4d3e; }
  .stage {
    position: relative; width: 100%; height: calc(100% - 45px); overflow: hidden; cursor: grab;
    touch-action: none;
    background-image: radial-gradient(#e4dfd5 1px, transparent 1px); background-size: 20px 20px;
  }
  .stage:active { cursor: grabbing; }
  html.theme-dark, html.theme-dark body { background: #0f172a; color: #e2e8f0; }
  html.theme-dark .outline { background: #0f172a; color: #e2e8f0; }
  html.theme-dark .outline h1 { color: #38bdf8; }
  svg { width: 100%; height: 100%; display: block; }
  .node { cursor: pointer; }
  .node rect { transition: filter .15s ease; }
  .node:hover rect { filter: brightness(0.97); }
  .outline {
    display: none; height: calc(100% - 45px); overflow-y: auto;
    padding: 24px 28px; background: #ffffff; line-height: 1.7;
  }
  html.embedded .bar { display: none; }
  html.embedded .stage, html.embedded .outline { height: 100%; }
  .outline.on { display: block; }
  .stage.off { display: none; }
  .outline ul { padding-left: 22px; margin: 4px 0; }
  .outline li { margin: 4px 0; }
  .outline h1 { font-size: 20px; margin-bottom: 12px; color: #1b4d3e; }
"""

_MINDMAP_HTML_JS = """
  const RAW = __PAYLOAD__;
  const PALETTE = ['#1b4d3e', '#2e6f5b', '#b45309', '#2563eb', '#7c3aed', '#0f766e', '#be185d'];
  const norm = (n, depth = 0, branch = 0) => ({
    label: String(n.title || n.name || '節點').trim(),
    depth, branch, collapsed: depth >= 2 && (n.children || []).length > 0,
    children: (n.children || []).map((c, i) => norm(c, depth + 1, depth === 0 ? i : branch)),
  });
  const ROOT = norm(RAW);
  document.getElementById('mmTitle').textContent = ROOT.label;
  const svg = document.getElementById('svg');
  const stage = document.getElementById('stage');
  const outlineEl = document.getElementById('outline');
  let pan = { x: 40, y: 40, scale: 1 };

  function measureText(str, fontSize) {
    const c = measureText.ctx || (measureText.ctx = document.createElement('canvas').getContext('2d'));
    c.font = `600 ${fontSize}px -apple-system, BlinkMacSystemFont, "PingFang TC", sans-serif`;
    return Math.min(260, Math.max(68, Math.ceil(c.measureText(str).width) + 28));
  }
  function wrapLabel(str, maxW, fontSize) {
    const c = measureText.ctx || (measureText.ctx = document.createElement('canvas').getContext('2d'));
    c.font = `600 ${fontSize}px -apple-system, BlinkMacSystemFont, "PingFang TC", sans-serif`;
    const lines = []; let cur = '';
    for (const ch of str) {
      if (c.measureText(cur + ch).width > maxW - 24 && cur) { lines.push(cur); cur = ch; }
      else cur += ch;
    }
    if (cur) lines.push(cur);
    return lines.slice(0, 3);
  }
  function layoutTree(node, x = 0) {
    const fs = node.depth === 0 ? 15 : 13;
    const w = measureText(node.label, fs);
    const lines = wrapLabel(node.label, w, fs);
    const h = Math.max(36, lines.length * 18 + 18);
    node.w = w; node.h = h; node.lines = lines; node.fs = fs; node.x = x;
    const kids = node.collapsed ? [] : node.children;
    if (!kids.length) { node.subH = h; return h; }
    const gapX = 56, gapY = 14;
    let totalH = 0;
    kids.forEach((k, i) => { totalH += layoutTree(k, x + w + gapX) + (i ? gapY : 0); });
    node.subH = Math.max(h, totalH);
    return node.subH;
  }
  function assignY(node, topY = 0) {
    const kids = node.collapsed ? [] : node.children;
    if (!kids.length) { node.y = topY + (node.subH - node.h) / 2; return; }
    const gapY = 14;
    let cy = topY;
    kids.forEach(k => { assignY(k, cy); cy += k.subH + gapY; });
    const first = kids[0], last = kids[kids.length - 1];
    node.y = ((first.y + first.h / 2) + (last.y + last.h / 2)) / 2 - node.h / 2;
  }
  function collect(node, nodes = [], edges = []) {
    nodes.push(node);
    if (!node.collapsed) {
      node.children.forEach(k => { edges.push([node, k]); collect(k, nodes, edges); });
    }
    return { nodes, edges };
  }
  const THEMES = {
    forest: {
      bg: '#faf8f4', dot: '#e4dfd5', nodeFill: '#ffffff', text: '#1f2421',
      pal: ['#1b4d3e', '#2e6f5b', '#b45309', '#2563eb', '#7c3aed', '#0f766e', '#be185d'],
    },
    dark: {
      bg: '#0f172a', dot: '#334155', nodeFill: '#1e293b', text: '#e2e8f0',
      pal: ['#0284c7', '#38bdf8', '#fbbf24', '#60a5fa', '#a78bfa', '#2dd4bf', '#f472b6'],
    },
    ocean: {
      bg: '#f0f7ff', dot: '#d4e4f7', nodeFill: '#ffffff', text: '#0f172a',
      pal: ['#0369a1', '#0284c7', '#0d9488', '#2563eb', '#4f46e5', '#0891b2', '#6366f1'],
    },
    warm: {
      bg: '#fdf8f3', dot: '#ecdcc9', nodeFill: '#fffcf8', text: '#292018',
      pal: ['#9a3412', '#c2410c', '#b45309', '#be123c', '#a16207', '#0f766e', '#7c2d12'],
    },
    mono: {
      bg: '#fafafa', dot: '#e5e5e5', nodeFill: '#ffffff', text: '#171717',
      pal: ['#171717', '#404040', '#525252', '#737373', '#262626', '#404040', '#525252'],
    },
  };
  const DENSITY = { compact: { gx: 38, gy: 8 }, normal: { gx: 56, gy: 14 }, relaxed: { gx: 78, gy: 22 } };
  const FONTS = { sm: { root: 13.5, leaf: 11.5 }, md: { root: 15, leaf: 13 }, lg: { root: 17, leaf: 14.5 } };
  const DEFAULT_CFG = {
    layout: 'tree-right', theme: 'forest', nodeShape: 'rounded',
    connector: 'curve', bg: 'dots', fontSize: 'md', density: 'normal',
  };
  let styleCfg = { ...DEFAULT_CFG };
  try {
    const saved = JSON.parse(localStorage.getItem('nb_mindmap_style') || 'null');
    if (saved && typeof saved === 'object') styleCfg = { ...DEFAULT_CFG, ...saved };
  } catch (e) {}
  const gaps = () => DENSITY[styleCfg.density] || DENSITY.normal;
  function layoutRight(node, x = 0) {
    const kids = node.collapsed ? [] : node.children;
    node.x = x; node.dir = 1;
    if (!kids.length) { node.subH = node.h; return node.h; }
    const { gx, gy } = gaps();
    let totalH = 0;
    kids.forEach((k, i) => { totalH += layoutRight(k, x + node.w + gx) + (i ? gy : 0); });
    node.subH = Math.max(node.h, totalH);
    return node.subH;
  }
  function layoutLeft(node, rightEdge) {
    const kids = node.collapsed ? [] : node.children;
    node.x = rightEdge - node.w; node.dir = -1;
    if (!kids.length) { node.subH = node.h; return node.h; }
    const { gx, gy } = gaps();
    let totalH = 0;
    kids.forEach((k, i) => { totalH += layoutLeft(k, node.x - gx) + (i ? gy : 0); });
    node.subH = Math.max(node.h, totalH);
    return node.subH;
  }
  function layoutOrgW(node) {
    const kids = node.collapsed ? [] : node.children;
    if (!kids.length) { node.subW = node.w; return node.w; }
    const gx = Math.max(16, Math.round(gaps().gx * 0.45));
    let totalW = 0;
    kids.forEach((k, i) => { totalW += layoutOrgW(k) + (i ? gx : 0); });
    node.subW = Math.max(node.w, totalW);
    return node.subW;
  }
  function assignOrgPos(node, leftX, topY) {
    node.x = leftX + (node.subW - node.w) / 2;
    node.y = topY;
    const kids = node.collapsed ? [] : node.children;
    if (!kids.length) return;
    const gx = Math.max(16, Math.round(gaps().gx * 0.45)), gy = gaps().gy * 3 + 6;
    const totalKidsW = kids.reduce((s, k, i) => s + k.subW + (i ? gx : 0), 0);
    let cx = leftX + Math.max(0, (node.subW - totalKidsW) / 2);
    kids.forEach(k => { assignOrgPos(k, cx, topY + node.h + gy); cx += k.subW + gx; });
  }
  function computeLayout() {
    const { nodes } = collect(ROOT);
    const fCfg = FONTS[styleCfg.fontSize] || FONTS.md;
    nodes.forEach(n => {
      const fs = n.depth === 0 ? fCfg.root : fCfg.leaf;
      n.fs = fs; n.w = measureText(n.label, fs); n.lines = wrapLabel(n.label, n.w, fs);
      n.h = Math.max(36, n.lines.length * (fs + 5) + 18); n.dir = 1;
    });
    if (styleCfg.layout === 'org-down') { layoutOrgW(ROOT); assignOrgPos(ROOT, 0, 0); return; }
    if (styleCfg.layout === 'tree-bilateral') {
      ROOT.x = 0;
      const kids = ROOT.collapsed ? [] : ROOT.children;
      const mid = Math.ceil(kids.length / 2);
      const rKids = kids.slice(0, mid), lKids = kids.slice(mid);
      const { gx, gy } = gaps();
      const rH = rKids.reduce((s, k, i) => s + layoutRight(k, ROOT.w + gx) + (i ? gy : 0), 0);
      const lH = lKids.reduce((s, k, i) => s + layoutLeft(k, -gx) + (i ? gy : 0), 0);
      const maxH = Math.max(ROOT.h, rH, lH);
      let ry = (maxH - rH) / 2;
      rKids.forEach(k => { assignY(k, ry); ry += k.subH + gy; });
      let ly = (maxH - lH) / 2;
      lKids.forEach(k => { assignY(k, ly); ly += k.subH + gy; });
      ROOT.y = (maxH - ROOT.h) / 2;
      return;
    }
    layoutRight(ROOT, 0);
    const walkY = (node, topY = 0) => {
      const kids = node.collapsed ? [] : node.children;
      if (!kids.length) { node.y = topY + (node.subH - node.h) / 2; return; }
      const { gy } = gaps();
      let cy = topY;
      kids.forEach(k => { walkY(k, cy); cy += k.subH + gy; });
      const first = kids[0], last = kids[kids.length - 1];
      node.y = ((first.y + first.h / 2) + (last.y + last.h / 2)) / 2 - node.h / 2;
    };
    walkY(ROOT, 0);
  }
  function applyCanvasStyle() {
    const th = THEMES[styleCfg.theme] || THEMES.forest;
    document.documentElement.classList.toggle('theme-dark', styleCfg.theme === 'dark');
    document.documentElement.style.background = th.bg;
    document.body.style.background = th.bg;
    stage.style.backgroundColor = th.bg;
    if (styleCfg.bg === 'grid') {
      stage.style.backgroundImage =
        `linear-gradient(${th.dot} 1px, transparent 1px), ` +
        `linear-gradient(90deg, ${th.dot} 1px, transparent 1px)`;
      stage.style.backgroundSize = '24px 24px';
    } else if (styleCfg.bg === 'solid') {
      stage.style.backgroundImage = 'none';
    } else {
      stage.style.backgroundImage = `radial-gradient(${th.dot} 1px, transparent 1px)`;
      stage.style.backgroundSize = '20px 20px';
    }
  }
  function edgePath(p, c) {
    const conn = styleCfg.connector || 'curve';
    if (styleCfg.layout === 'org-down') {
      const x1 = p.x + p.w / 2, y1 = p.y + p.h, x2 = c.x + c.w / 2, y2 = c.y, my = (y1 + y2) / 2;
      if (conn === 'straight') return `M${x1},${y1} L${x2},${y2}`;
      if (conn === 'elbow') return `M${x1},${y1} L${x1},${my} L${x2},${my} L${x2},${y2}`;
      return `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`;
    }
    const goLeft = c.dir < 0;
    const x1 = goLeft ? p.x : p.x + p.w, y1 = p.y + p.h / 2;
    const x2 = goLeft ? c.x + c.w : c.x, y2 = c.y + c.h / 2, mx = (x1 + x2) / 2;
    if (conn === 'straight') return `M${x1},${y1} L${x2},${y2}`;
    if (conn === 'elbow') return `M${x1},${y1} L${mx},${y1} L${mx},${y2} L${x2},${y2}`;
    return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
  }
  function render() {
    applyCanvasStyle();
    computeLayout();
    const { nodes, edges } = collect(ROOT);
    const ns = 'http://www.w3.org/2000/svg';
    const th = THEMES[styleCfg.theme] || THEMES.forest;
    const pal = th.pal;
    svg.innerHTML = '';
    const g = document.createElementNS(ns, 'g');
    g.setAttribute('transform', `translate(${pan.x},${pan.y}) scale(${pan.scale})`);
    edges.forEach(([p, c]) => {
      const path = document.createElementNS(ns, 'path');
      path.setAttribute('d', edgePath(p, c));
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', pal[(c.branch % (pal.length - 1)) + 1]);
      path.setAttribute('stroke-opacity', styleCfg.theme === 'dark' ? '0.68' : '0.48');
      path.setAttribute('stroke-width', c.depth === 1 ? '2.4' : '1.6');
      g.appendChild(path);
    });
    nodes.forEach(n => {
      const grp = document.createElementNS(ns, 'g');
      grp.setAttribute('class', 'node');
      const col = n.depth === 0 ? pal[0] : pal[(n.branch % (pal.length - 1)) + 1];
      const rx = styleCfg.nodeShape === 'pill'
        ? Math.round(n.h / 2)
        : (styleCfg.nodeShape === 'sharp' ? 2 : (n.depth === 0 ? 12 : 9));
      if (styleCfg.nodeShape === 'underline' && n.depth > 0) {
        const hit = document.createElementNS(ns, 'rect');
        hit.setAttribute('x', n.x); hit.setAttribute('y', n.y);
        hit.setAttribute('width', n.w); hit.setAttribute('height', n.h);
        hit.setAttribute('fill', 'transparent');
        grp.appendChild(hit);
        const ln = document.createElementNS(ns, 'line');
        ln.setAttribute('x1', n.x + 4); ln.setAttribute('y1', n.y + n.h - 2);
        ln.setAttribute('x2', n.x + n.w - 4); ln.setAttribute('y2', n.y + n.h - 2);
        ln.setAttribute('stroke', col); ln.setAttribute('stroke-width', n.depth === 1 ? '2.4' : '1.6');
        grp.appendChild(ln);
      } else {
        const rect = document.createElementNS(ns, 'rect');
        rect.setAttribute('x', n.x); rect.setAttribute('y', n.y);
        rect.setAttribute('width', n.w); rect.setAttribute('height', n.h);
        rect.setAttribute('rx', rx);
        rect.setAttribute('fill', n.depth === 0 ? col : th.nodeFill);
        rect.setAttribute('stroke', col);
        rect.setAttribute('stroke-width', n.depth === 0 ? '0' : (n.depth === 1 ? '1.8' : '1.2'));
        grp.appendChild(rect);
      }
      n.lines.forEach((ln, idx) => {
        const txt = document.createElementNS(ns, 'text');
        txt.setAttribute('x', n.x + 12);
        txt.setAttribute('y', n.y + 18 + idx * (n.fs + 5));
        txt.setAttribute('font-size', n.fs);
        txt.setAttribute('font-weight', n.depth <= 1 ? '600' : '500');
        txt.setAttribute('fill', n.depth === 0 ? '#ffffff' : th.text);
        txt.textContent = ln;
        grp.appendChild(txt);
      });
      if (n.children.length) {
        const badge = document.createElementNS(ns, 'text');
        if (styleCfg.layout === 'org-down') {
          badge.setAttribute('x', n.x + n.w / 2 - 6); badge.setAttribute('y', n.y + n.h + 13);
        } else {
          badge.setAttribute('x', n.dir < 0 ? n.x - 18 : n.x + n.w + 8);
          badge.setAttribute('y', n.y + n.h / 2 + 4);
        }
        badge.setAttribute('font-size', '11');
        badge.setAttribute('fill', col);
        badge.setAttribute('font-weight', '600');
        badge.textContent = n.collapsed ? `+${n.children.length}` : '−';
        grp.appendChild(badge);
        grp.addEventListener('click', e => {
          e.stopPropagation(); n.collapsed = !n.collapsed; render();
        });
      }
      g.appendChild(grp);
    });
    svg.appendChild(g);
  }
  function fitView() {
    computeLayout();
    const { nodes } = collect(ROOT);
    const minX = Math.min(...nodes.map(n => n.x)), maxX = Math.max(...nodes.map(n => n.x + n.w));
    const minY = Math.min(...nodes.map(n => n.y)), maxY = Math.max(...nodes.map(n => n.y + n.h));
    const bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);
    const sw = stage.clientWidth || 800, sh = stage.clientHeight || 500;
    const s = Math.min(1.05, Math.max(0.28, Math.min((sw - 64) / (bw + 40), (sh - 48) / (bh + 24))));
    pan = { scale: s, x: (sw - bw * s) / 2 - minX * s, y: Math.max(20, (sh - bh * s) / 2 - minY * s) };
    render();
  }
  const esc = s => s.replace(/</g, '&lt;');
  function buildOutline(n) {
    if (!n.children.length) return `<li>${esc(n.label)}</li>`;
    return `<li><b>${esc(n.label)}</b><ul>${n.children.map(buildOutline).join('')}</ul></li>`;
  }
  outlineEl.innerHTML = `<h1>${esc(ROOT.label)}</h1><ul>${ROOT.children.map(buildOutline).join('')}</ul>`;
  const zoomBy = k => { pan.scale = Math.min(2.2, Math.max(0.25, pan.scale * k)); render(); };
  if (window.self !== window.top) document.documentElement.classList.add('embedded');
  const toggleOutline = () => {
    const on = outlineEl.classList.toggle('on');
    stage.classList.toggle('off', on);
    document.getElementById('btnOutline').classList.toggle('on', on);
    return on;
  };
  let allExpanded = false;
  const toggleExpandAll = () => {
    allExpanded = !allExpanded;
    const walk = n => {
      n.collapsed = allExpanded ? false : (n.depth >= 2 && n.children.length > 0);
      n.children.forEach(walk);
    };
    walk(ROOT);
    const b = document.getElementById('btnExpandAll');
    if (b) {
      b.textContent = allExpanded ? '收合節點' : '全部展開';
      b.classList.toggle('on', allExpanded);
    }
    fitView();
  };
  const applyStyle = (partial, refit = true) => {
    const prevLayout = styleCfg.layout;
    styleCfg = { ...DEFAULT_CFG, ...(partial || {}) };
    try { localStorage.setItem('nb_mindmap_style', JSON.stringify(styleCfg)); } catch (e) {}
    const sel = document.getElementById('selTemplate');
    if (sel) sel.value = styleCfg.layout;
    if (refit || prevLayout !== styleCfg.layout) fitView();
    else render();
  };
  const setTemplate = tpl => {
    if (tpl === 'dark') applyStyle({ ...styleCfg, theme: 'dark' }, false);
    else applyStyle({ ...styleCfg, layout: tpl || 'tree-right' }, true);
  };
  const exportSvg = () => {
    const clone = svg.cloneNode(true);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    const th = THEMES[styleCfg.theme] || THEMES.forest;
    clone.style.background = th.bg;
    const blob = new Blob([clone.outerHTML], { type: 'image/svg+xml;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${(ROOT.label || 'mindmap').slice(0, 40)}.svg`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  const selTpl = document.getElementById('selTemplate');
  if (selTpl) { selTpl.value = styleCfg.layout; selTpl.onchange = e => setTemplate(e.target.value); }
  document.getElementById('btnZoomIn').onclick = () => zoomBy(1.18);
  document.getElementById('btnZoomOut').onclick = () => zoomBy(1 / 1.18);
  document.getElementById('btnFit').onclick = fitView;
  document.getElementById('btnExpandAll').onclick = toggleExpandAll;
  document.getElementById('btnOutline').onclick = () => toggleOutline();
  window.addEventListener('message', e => {
    if (!e.data || e.data.type !== 'mindmap-cmd') return;
    if (e.data.cmd === 'zoomIn') zoomBy(1.18);
    else if (e.data.cmd === 'zoomOut') zoomBy(1 / 1.18);
    else if (e.data.cmd === 'fit') fitView();
    else if (e.data.cmd === 'expandAll') toggleExpandAll();
    else if (e.data.cmd === 'toggleOutline') toggleOutline();
    else if (e.data.cmd === 'setTemplate') setTemplate(e.data.value);
    else if (e.data.cmd === 'applyStyle') applyStyle(e.data.value, true);
    else if (e.data.cmd === 'exportSvg') exportSvg();
  });
  const pts = new Map();
  let pinchDist = null;
  stage.addEventListener('pointerdown', e => {
    if (e.target.closest('.node') && pts.size === 0) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.size === 2) {
      const [a, b] = [...pts.values()];
      pinchDist = Math.hypot(a.x - b.x, a.y - b.y);
    }
  });
  window.addEventListener('pointermove', e => {
    if (!pts.has(e.pointerId)) return;
    const prev = pts.get(e.pointerId);
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.size === 1) {
      pan.x += e.clientX - prev.x; pan.y += e.clientY - prev.y; render();
    } else if (pts.size === 2) {
      const [a, b] = [...pts.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinchDist && d > 0) {
        const rect = stage.getBoundingClientRect();
        const mx = (a.x + b.x) / 2 - rect.left, my = (a.y + b.y) / 2 - rect.top;
        const nextScale = Math.min(2.2, Math.max(0.25, pan.scale * (d / pinchDist)));
        const k = nextScale / pan.scale;
        pan.x = mx - (mx - pan.x) * k; pan.y = my - (my - pan.y) * k; pan.scale = nextScale;
        render();
      }
      pinchDist = d;
    }
  });
  const endPtr = e => { pts.delete(e.pointerId); if (pts.size < 2) pinchDist = null; };
  window.addEventListener('pointerup', endPtr);
  window.addEventListener('pointercancel', endPtr);
  ['gesturestart', 'gesturechange', 'gestureend'].forEach(ev =>
    stage.addEventListener(ev, e => e.preventDefault(), { passive: false })
  );
  stage.addEventListener('wheel', e => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault(); zoomBy(e.deltaY < 0 ? 1.08 : 0.92);
    }
  }, { passive: false });
  fitView();
"""

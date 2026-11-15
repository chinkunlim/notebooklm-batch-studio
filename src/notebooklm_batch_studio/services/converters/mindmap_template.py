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
  html.theme-dark .stage { background-image: radial-gradient(#334155 1px, transparent 1px); }
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
  let template = 'tree-right';
  const DARK_PALETTE = ['#0284c7', '#38bdf8', '#fbbf24', '#60a5fa', '#a78bfa', '#2dd4bf', '#f472b6'];
  function layoutRight(node, x = 0) {
    const kids = node.collapsed ? [] : node.children;
    node.x = x; node.dir = 1;
    if (!kids.length) { node.subH = node.h; return node.h; }
    const gapX = 56, gapY = 14;
    let totalH = 0;
    kids.forEach((k, i) => { totalH += layoutRight(k, x + node.w + gapX) + (i ? gapY : 0); });
    node.subH = Math.max(node.h, totalH);
    return node.subH;
  }
  function layoutLeft(node, rightEdge) {
    const kids = node.collapsed ? [] : node.children;
    node.x = rightEdge - node.w; node.dir = -1;
    if (!kids.length) { node.subH = node.h; return node.h; }
    const gapX = 56, gapY = 14;
    let totalH = 0;
    kids.forEach((k, i) => { totalH += layoutLeft(k, node.x - gapX) + (i ? gapY : 0); });
    node.subH = Math.max(node.h, totalH);
    return node.subH;
  }
  function layoutOrgW(node) {
    const kids = node.collapsed ? [] : node.children;
    if (!kids.length) { node.subW = node.w; return node.w; }
    const gapX = 24;
    let totalW = 0;
    kids.forEach((k, i) => { totalW += layoutOrgW(k) + (i ? gapX : 0); });
    node.subW = Math.max(node.w, totalW);
    return node.subW;
  }
  function assignOrgPos(node, leftX, topY) {
    node.x = leftX + (node.subW - node.w) / 2;
    node.y = topY;
    const kids = node.collapsed ? [] : node.children;
    if (!kids.length) return;
    const gapX = 24, gapY = 48;
    const totalKidsW = kids.reduce((s, k, i) => s + k.subW + (i ? gapX : 0), 0);
    let cx = leftX + Math.max(0, (node.subW - totalKidsW) / 2);
    kids.forEach(k => { assignOrgPos(k, cx, topY + node.h + gapY); cx += k.subW + gapX; });
  }
  function computeLayout() {
    const { nodes } = collect(ROOT);
    nodes.forEach(n => {
      const fs = n.depth === 0 ? 15 : 13;
      n.fs = fs; n.w = measureText(n.label, fs); n.lines = wrapLabel(n.label, n.w, fs);
      n.h = Math.max(36, n.lines.length * 18 + 18); n.dir = 1;
    });
    if (template === 'org-down') {
      layoutOrgW(ROOT); assignOrgPos(ROOT, 0, 0); return;
    }
    if (template === 'tree-bilateral') {
      ROOT.x = 0;
      const kids = ROOT.collapsed ? [] : ROOT.children;
      const mid = Math.ceil(kids.length / 2);
      const rKids = kids.slice(0, mid), lKids = kids.slice(mid);
      const gapX = 56, gapY = 14;
      const rH = rKids.reduce((s, k, i) => s + layoutRight(k, ROOT.w + gapX) + (i ? gapY : 0), 0);
      const lH = lKids.reduce((s, k, i) => s + layoutLeft(k, -gapX) + (i ? gapY : 0), 0);
      const maxH = Math.max(ROOT.h, rH, lH);
      let ry = (maxH - rH) / 2;
      rKids.forEach(k => { assignY(k, ry); ry += k.subH + gapY; });
      let ly = (maxH - lH) / 2;
      lKids.forEach(k => { assignY(k, ly); ly += k.subH + gapY; });
      ROOT.y = (maxH - ROOT.h) / 2;
      return;
    }
    layoutTree(ROOT, 0); assignY(ROOT, 0);
  }
  function render() {
    computeLayout();
    const { nodes, edges } = collect(ROOT);
    const ns = 'http://www.w3.org/2000/svg';
    const isDark = template === 'dark';
    const pal = isDark ? DARK_PALETTE : PALETTE;
    svg.innerHTML = '';
    const g = document.createElementNS(ns, 'g');
    g.setAttribute('transform', `translate(${pan.x},${pan.y}) scale(${pan.scale})`);
    edges.forEach(([p, c]) => {
      let d;
      if (template === 'org-down') {
        const x1 = p.x + p.w / 2, y1 = p.y + p.h, x2 = c.x + c.w / 2, y2 = c.y, my = (y1 + y2) / 2;
        d = `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`;
      } else {
        const goLeft = c.dir < 0;
        const x1 = goLeft ? p.x : p.x + p.w, y1 = p.y + p.h / 2;
        const x2 = goLeft ? c.x + c.w : c.x, y2 = c.y + c.h / 2, mx = (x1 + x2) / 2;
        d = `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
      }
      const path = document.createElementNS(ns, 'path');
      path.setAttribute('d', d);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', pal[(c.branch % (pal.length - 1)) + 1]);
      path.setAttribute('stroke-opacity', isDark ? '0.65' : '0.45');
      path.setAttribute('stroke-width', c.depth === 1 ? '2.4' : '1.6');
      g.appendChild(path);
    });
    nodes.forEach(n => {
      const grp = document.createElementNS(ns, 'g');
      grp.setAttribute('class', 'node');
      const col = n.depth === 0 ? pal[0] : pal[(n.branch % (pal.length - 1)) + 1];
      const rect = document.createElementNS(ns, 'rect');
      rect.setAttribute('x', n.x); rect.setAttribute('y', n.y);
      rect.setAttribute('width', n.w); rect.setAttribute('height', n.h);
      rect.setAttribute('rx', n.depth === 0 ? 12 : 9);
      rect.setAttribute('fill', n.depth === 0 ? col : (isDark ? '#1e293b' : '#ffffff'));
      rect.setAttribute('stroke', col);
      rect.setAttribute('stroke-width', n.depth === 0 ? '0' : (n.depth === 1 ? '1.8' : '1.2'));
      grp.appendChild(rect);
      n.lines.forEach((ln, idx) => {
        const txt = document.createElementNS(ns, 'text');
        txt.setAttribute('x', n.x + 12);
        txt.setAttribute('y', n.y + 18 + idx * 18);
        txt.setAttribute('font-size', n.fs);
        txt.setAttribute('font-weight', n.depth <= 1 ? '600' : '500');
        txt.setAttribute('fill', n.depth === 0 ? '#ffffff' : (isDark ? '#e2e8f0' : '#1f2421'));
        txt.textContent = ln;
        grp.appendChild(txt);
      });
      if (n.children.length) {
        const badge = document.createElementNS(ns, 'text');
        if (template === 'org-down') {
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
  const setTemplate = tpl => {
    template = tpl || 'tree-right';
    document.documentElement.classList.toggle('theme-dark', template === 'dark');
    const sel = document.getElementById('selTemplate');
    if (sel) sel.value = template;
    fitView();
  };
  const selTpl = document.getElementById('selTemplate');
  if (selTpl) selTpl.onchange = e => setTemplate(e.target.value);
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

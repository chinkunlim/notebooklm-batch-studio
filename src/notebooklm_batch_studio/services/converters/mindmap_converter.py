"""Mind map converter: transforms Gemini Notebook tree structures into OPML, Markdown, and JSON.

Supports XMind/MindNode-compatible OPML 2.0 XML exports, clean Markdown hierarchical
bullet outlines, and normalized JSON structures.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from notebooklm_batch_studio.domain.models import MindMapNode

logger = logging.getLogger(__name__)


def parse_notebooklm_mindmap(raw_data: dict[str, Any]) -> MindMapNode:
    """Recursively parse Gemini Notebook raw mind map JSON into a domain MindMapNode tree.

    Args:
        raw_data: Dictionary containing 'name' and optional 'children' list.

    Returns:
        Root MindMapNode representing the hierarchy.
    """
    title = str(raw_data.get("name", "Mind Map")).strip()
    raw_children = raw_data.get("children", [])

    children_nodes: list[MindMapNode] = []
    if isinstance(raw_children, list):
        for ch in raw_children:
            if isinstance(ch, dict):
                children_nodes.append(parse_notebooklm_mindmap(ch))

    return MindMapNode(title=title, children=children_nodes)


def _node_to_dict(node: MindMapNode) -> dict[str, Any]:
    """Convert MindMapNode to a standard nested dictionary.

    Args:
        node: The MindMapNode to convert.

    Returns:
        Dictionary representation of the node and its children.
    """
    return {
        "title": node.title,
        "children": [_node_to_dict(c) for c in node.children],
    }


def to_json(root: MindMapNode) -> str:
    """Serialize MindMapNode tree into standard JSON format.

    Args:
        root: The root MindMapNode.

    Returns:
        JSON string representation.
    """
    payload = _node_to_dict(root)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_opml_outlines(node: MindMapNode, depth: int = 2) -> str:
    """Recursively build OPML outline XML tags.

    Args:
        node: Current MindMapNode.
        depth: Indentation depth.

    Returns:
        OPML XML string slice.
    """
    indent = "  " * depth
    text_attr = quoteattr(node.title)

    if not node.children:
        return f"{indent}<outline text={text_attr} />\n"

    res = f"{indent}<outline text={text_attr}>\n"
    for child in node.children:
        res += _build_opml_outlines(child, depth + 1)
    res += f"{indent}</outline>\n"
    return res


def to_opml(root: MindMapNode, title: str | None = None) -> str:
    """Convert MindMapNode tree to OPML 2.0 XML format for XMind/MindNode import.

    Args:
        root: The root MindMapNode.
        title: Optional document title for OPML head.

    Returns:
        Valid OPML 2.0 XML string.
    """
    doc_title = escape(title or root.title)
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        "  <head>",
        f"    <title>{doc_title}</title>",
        "  </head>",
        "  <body>",
        _build_opml_outlines(root, depth=2).rstrip(),
        "  </body>",
        "</opml>",
        "",
    ]
    return "\n".join(lines)


def _build_markdown_lines(node: MindMapNode, level: int) -> list[str]:
    """Recursively build Markdown bullet points.

    Args:
        node: Current MindMapNode.
        level: Current nesting depth (0 for root).

    Returns:
        List of Markdown formatted lines.
    """
    lines: list[str] = []
    if level == 0:
        lines.append(f"# {node.title}\n")
    else:
        indent = "  " * (level - 1)
        lines.append(f"{indent}- {node.title}")

    for child in node.children:
        lines.extend(_build_markdown_lines(child, level + 1))

    return lines


def to_markdown(root: MindMapNode) -> str:
    """Convert MindMapNode tree to an indented hierarchical Markdown list.

    Args:
        root: The root MindMapNode.

    Returns:
        Markdown outline string.
    """
    lines = _build_markdown_lines(root, level=0)
    return "\n".join(lines) + "\n"


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
    background-image: radial-gradient(#e4dfd5 1px, transparent 1px); background-size: 20px 20px;
  }
  .stage:active { cursor: grabbing; }
  svg { width: 100%; height: 100%; display: block; }
  .node { cursor: pointer; }
  .node rect { transition: filter .15s ease; }
  .node:hover rect { filter: brightness(0.97); }
  .outline {
    display: none; height: calc(100% - 45px); overflow-y: auto;
    padding: 24px 28px; background: #ffffff; line-height: 1.7;
  }
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
  function render() {
    layoutTree(ROOT, 0);
    assignY(ROOT, 0);
    const { nodes, edges } = collect(ROOT);
    const ns = 'http://www.w3.org/2000/svg';
    svg.innerHTML = '';
    const g = document.createElementNS(ns, 'g');
    g.setAttribute('transform', `translate(${pan.x},${pan.y}) scale(${pan.scale})`);
    edges.forEach(([p, c]) => {
      const x1 = p.x + p.w, y1 = p.y + p.h / 2, x2 = c.x, y2 = c.y + c.h / 2;
      const mx = (x1 + x2) / 2;
      const path = document.createElementNS(ns, 'path');
      path.setAttribute('d', `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', PALETTE[(c.branch % (PALETTE.length - 1)) + 1]);
      path.setAttribute('stroke-opacity', '0.45');
      path.setAttribute('stroke-width', c.depth === 1 ? '2.4' : '1.6');
      g.appendChild(path);
    });
    nodes.forEach(n => {
      const grp = document.createElementNS(ns, 'g');
      grp.setAttribute('class', 'node');
      const col = n.depth === 0 ? PALETTE[0] : PALETTE[(n.branch % (PALETTE.length - 1)) + 1];
      const rect = document.createElementNS(ns, 'rect');
      rect.setAttribute('x', n.x); rect.setAttribute('y', n.y);
      rect.setAttribute('width', n.w); rect.setAttribute('height', n.h);
      rect.setAttribute('rx', n.depth === 0 ? 12 : 9);
      rect.setAttribute('fill', n.depth === 0 ? col : '#ffffff');
      rect.setAttribute('stroke', col);
      rect.setAttribute('stroke-width', n.depth === 0 ? '0' : (n.depth === 1 ? '1.8' : '1.2'));
      grp.appendChild(rect);
      n.lines.forEach((ln, idx) => {
        const txt = document.createElementNS(ns, 'text');
        txt.setAttribute('x', n.x + 12);
        txt.setAttribute('y', n.y + 18 + idx * 18);
        txt.setAttribute('font-size', n.fs);
        txt.setAttribute('font-weight', n.depth <= 1 ? '600' : '500');
        txt.setAttribute('fill', n.depth === 0 ? '#ffffff' : '#1f2421');
        txt.textContent = ln;
        grp.appendChild(txt);
      });
      if (n.children.length) {
        const badge = document.createElementNS(ns, 'text');
        badge.setAttribute('x', n.x + n.w + 8);
        badge.setAttribute('y', n.y + n.h / 2 + 4);
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
    layoutTree(ROOT, 0); assignY(ROOT, 0);
    const { nodes } = collect(ROOT);
    const maxX = Math.max(...nodes.map(n => n.x + n.w));
    const maxY = Math.max(...nodes.map(n => n.y + n.h));
    const sw = stage.clientWidth || 800, sh = stage.clientHeight || 500;
    const s = Math.min(1.05, Math.max(0.35, Math.min((sw - 64) / (maxX + 40), (sh - 48) / (maxY + 20))));
    pan = { scale: s, x: 28, y: Math.max(20, (sh - maxY * s) / 2) };
    render();
  }
  const esc = s => s.replace(/</g, '&lt;');
  function buildOutline(n) {
    if (!n.children.length) return `<li>${esc(n.label)}</li>`;
    return `<li><b>${esc(n.label)}</b><ul>${n.children.map(buildOutline).join('')}</ul></li>`;
  }
  outlineEl.innerHTML = `<h1>${esc(ROOT.label)}</h1><ul>${ROOT.children.map(buildOutline).join('')}</ul>`;
  const zoomBy = k => { pan.scale = Math.min(2.2, Math.max(0.25, pan.scale * k)); render(); };
  document.getElementById('btnZoomIn').onclick = () => zoomBy(1.18);
  document.getElementById('btnZoomOut').onclick = () => zoomBy(1 / 1.18);
  document.getElementById('btnFit').onclick = fitView;
  document.getElementById('btnExpandAll').onclick = () => {
    const openAll = n => { n.collapsed = false; n.children.forEach(openAll); };
    openAll(ROOT); fitView();
  };
  document.getElementById('btnOutline').onclick = e => {
    const on = outlineEl.classList.toggle('on');
    stage.classList.toggle('off', on);
    e.currentTarget.classList.toggle('on', on);
  };
  let drag = null;
  stage.addEventListener('pointerdown', e => {
    if (!e.target.closest('.node')) drag = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  });
  window.addEventListener('pointermove', e => {
    if (!drag) return;
    pan.x = e.clientX - drag.x; pan.y = e.clientY - drag.y; render();
  });
  window.addEventListener('pointerup', () => { drag = null; });
  stage.addEventListener('wheel', e => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault(); zoomBy(e.deltaY < 0 ? 1.08 : 0.92);
    }
  }, { passive: false });
  fitView();
"""


def mindmap_to_html(title: str, tree_data: dict[str, Any]) -> str:
    """Render a mind map JSON tree as an interactive offline SVG mind map HTML page.

    Args:
        title: Document title shown in the page `<title>` and fallback root label.
        tree_data: Parsed JSON tree dictionary (`title`/`name` and `children`).

    Returns:
        Self-contained HTML document with an interactive SVG mind map and outline toggle.
    """
    safe_title = escape(title)
    payload_json = json.dumps(tree_data, ensure_ascii=False).replace("</", "<\\/")
    script = _MINDMAP_HTML_JS.replace("__PAYLOAD__", payload_json)
    return (
        f'<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{safe_title}</title><style>{_MINDMAP_HTML_CSS}</style></head><body>"
        f'<div class="bar"><span class="bar-title" id="mmTitle">{safe_title}</span>'
        f'<div class="tools"><button class="btn" id="btnZoomOut">－</button>'
        f'<button class="btn" id="btnFit">適應畫面</button>'
        f'<button class="btn" id="btnZoomIn">＋</button>'
        f'<button class="btn" id="btnExpandAll">全部展開</button>'
        f'<button class="btn" id="btnOutline">大綱文字</button></div></div>'
        f'<div class="stage" id="stage"><svg id="svg"></svg></div>'
        f'<div class="outline" id="outline"></div>'
        f"<script>{script}</script></body></html>"
    )

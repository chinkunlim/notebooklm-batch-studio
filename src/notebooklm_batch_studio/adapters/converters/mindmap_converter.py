"""Mind map converter: transforms NotebookLM tree structures into OPML, Markdown, and JSON.

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
    """Recursively parse NotebookLM raw mind map JSON into a domain MindMapNode tree.

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

"""Embedded HTML dashboard loader for local web management.

Reads the local standalone HTML dashboard from the package static resources.
"""

from __future__ import annotations

from pathlib import Path

_STATIC_DASHBOARD = Path(__file__).resolve().parent / "static" / "index.html"


def get_dashboard_html() -> str:
    """Return the complete dashboard HTML application.

    Returns:
        HTML string containing complete styles, markup, and vanilla JavaScript.
    """
    return _STATIC_DASHBOARD.read_text(encoding="utf-8")

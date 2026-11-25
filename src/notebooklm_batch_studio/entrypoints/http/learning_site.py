"""Serve Gemini-generated learning sites in a sandbox (SPEC-021, ADR-016).

A learning site is untrusted HTML with its own JavaScript. It is only served here, with a CSP that
blocks every network request and a `sandbox` directive that gives the page an opaque origin, so its
scripts cannot reach this app's pages or API even through `window.open`. Because a sandboxed page
has no `localStorage`, a small adapter is injected first: it keeps storage in memory, loads saved
progress from the `#nbs-site=` URL fragment and posts changes to the study workspace that framed it.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from notebooklm_batch_studio.entrypoints.http.artifacts import _resolve_artifact_path

logger = logging.getLogger(__name__)

learning_site_router = APIRouter()

SITE_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; "
    "font-src data:; media-src data: blob:; connect-src 'none'; form-action 'none'; base-uri 'none'; "
    "frame-ancestors 'self'; sandbox allow-scripts allow-modals allow-downloads"
)
STORAGE_SHIM_MARKER = "/*nbs-site-storage*/"
# Read once; inlined because the site's CSP allows no script files
_STORAGE_SHIM = (
    "<script>"
    + (Path(__file__).resolve().parents[1] / "static" / "site-storage-shim.js").read_text(encoding="utf-8")
    + "</script>"
)
_INSERT_AFTER = (
    re.compile(r"<head\b[^>]*>", re.I),
    re.compile(r"<html\b[^>]*>", re.I),
    re.compile(r"<!doctype[^>]*>", re.I),
)


def inject_storage_shim(html: str) -> str:
    """Put the storage adapter before any of the site's own scripts.

    Args:
        html: Site HTML as downloaded.

    Returns:
        HTML with the adapter right after `<head>` (or `<html>`, or the doctype, or at the start).
    """
    for pattern in _INSERT_AFTER:
        match = pattern.search(html)
        if match:
            return html[: match.end()] + _STORAGE_SHIM + html[match.end() :]
    return _STORAGE_SHIM + html


@learning_site_router.get(
    "/api/artifacts/{code}/site/{file_path:path}",
    tags=["Artifacts"],
    operation_id="view_learning_site",
)
def view_learning_site(code: str, file_path: str, request: Request) -> Response:
    """Open a downloaded learning site in a sandbox that cannot reach the app.

    Args:
        code: Course identifier.
        file_path: Course-relative path of the site's `.html` file.
        request: Incoming HTTP request context.

    Returns:
        The site HTML with the storage adapter and the sandboxing CSP.

    Raises:
        HTTPException: 403 on traversal, 404 if missing, 415 when the file is not HTML.
    """
    target = _resolve_artifact_path(request, code, file_path)
    if target.suffix.lower() != ".html":
        raise HTTPException(status_code=415, detail="Only learning-site HTML files can be opened here")
    html = inject_storage_shim(target.read_text(encoding="utf-8", errors="replace"))
    logger.info("learning site served course=%s file=%s", code, target.name)
    headers = {
        "Content-Security-Policy": SITE_CSP,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    }
    return Response(content=html, media_type="text/html; charset=utf-8", headers=headers)

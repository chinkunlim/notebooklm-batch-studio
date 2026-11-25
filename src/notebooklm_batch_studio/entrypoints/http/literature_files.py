"""FastAPI routes for literature PDF preview, APA 7 / report export, and study-layout migration (SPEC-012)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from notebooklm_batch_studio.entrypoints.http.literature import with_literature_manager

logger = logging.getLogger(__name__)
MIGRATE_RETIRED_DETAIL = (
    "migrate-study-layout 已停用，請改用 `uv run notebooklm-batch-studio consolidate`"
    "（先預覽，確認後加 --apply）"
)
literature_files_router = APIRouter()


@literature_files_router.get(
    "/api/literature/{key}/pdf", tags=["Literature"], operation_id="get_literature_pdf"
)
def get_literature_pdf_endpoint(key: str, request: Request) -> FileResponse:
    """Serve the downloaded PDF inline for browser preview.

    Args:
        key: Literature item key.
        request: HTTP request context.

    Returns:
        `FileResponse` with `application/pdf`.
    """
    session, manager, _ = with_literature_manager(request)
    try:
        pdf_path = manager.resolve_pdf_path(key)
        if pdf_path is None:
            raise HTTPException(status_code=404, detail=f"PDF not found for literature: {key}")
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline"},
        )
    finally:
        session.close()


@literature_files_router.get(
    "/api/literature/export/apa", tags=["Literature"], operation_id="export_literature_apa"
)
def export_literature_apa_endpoint(
    request: Request, course_code: str | None = None, keys: str | None = None
) -> dict[str, Any]:
    """Return sorted APA 7 citations in plain text and italic-preserving HTML.

    Args:
        request: HTTP request context.
        course_code: Optional course filter.
        keys: Optional comma-separated literature keys to include.

    Returns:
        Dictionary with `count`, `plain`, and `html`.
    """
    session, manager, _ = with_literature_manager(request)
    try:
        key_list = [k.strip() for k in keys.split(",") if k.strip()] if keys else None
        return manager.export_apa_list(course_code=course_code, keys=key_list)
    finally:
        session.close()


@literature_files_router.get(
    "/api/literature/export/report", tags=["Literature"], operation_id="export_literature_report"
)
def export_literature_report_endpoint(request: Request, course_code: str | None = None) -> PlainTextResponse:
    """Download the Markdown report of tracked literature items.

    Args:
        request: HTTP request context.
        course_code: Optional course filter.

    Returns:
        Markdown plain text response.
    """
    session, manager, _ = with_literature_manager(request)
    try:
        md = manager.export_report(course_code=course_code)
        return PlainTextResponse(
            md,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="literature_report.md"'},
        )
    finally:
        session.close()


@literature_files_router.post(
    "/api/courses/migrate-study-layout",
    tags=["Courses"],
    operation_id="migrate_study_layout",
    deprecated=True,
    status_code=410,
)
def migrate_study_layout_endpoint() -> None:
    """Retired: answer 410 and point to `consolidate` without reading the body or touching files.

    The old tool moved folders by default (dry_run defaulted to False) and once nearly moved courses
    out of their school-named folders (ISSUE-069). Refs: SPEC-023, ADR-018

    Raises:
        HTTPException: Always 410 Gone.
    """
    raise HTTPException(status_code=410, detail=MIGRATE_RETIRED_DETAIL)

"""FastAPI routes for literature PDF preview, APA 7 / report export, and study-layout migration (SPEC-012)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from notebooklm_batch_studio.adapters.db.study_migration_repo import StudyMigrationRepository
from notebooklm_batch_studio.entrypoints.http.literature import with_literature_manager
from notebooklm_batch_studio.services.study_migration import migrate_courses_to_study_hierarchy

logger = logging.getLogger(__name__)
literature_files_router = APIRouter()


class StudyMigrateRequest(BaseModel):
    """Request body for migrating legacy courses to `<term>/<subject>/<category>`.

    Attributes:
        dry_run: When True, return planned moves without modifying disk or DB.
    """

    dry_run: bool = False


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
    "/api/courses/migrate-study-layout", tags=["Courses"], operation_id="migrate_study_layout"
)
def migrate_study_layout_endpoint(req: StudyMigrateRequest, request: Request) -> dict[str, Any]:
    """Migrate existing legacy courses into `<STUDY_ROOT_DIR>/<term>/<subject>/<category>`.

    Args:
        req: Migration options (`dry_run`).
        request: HTTP request context.

    Returns:
        Summary of migrated or planned courses.
    """
    with request.app.state.session_factory() as session:
        return migrate_courses_to_study_hierarchy(
            StudyMigrationRepository(session), request.app.state.config, dry_run=req.dry_run
        )

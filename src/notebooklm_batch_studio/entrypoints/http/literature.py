"""FastAPI routes for literature fetching, APA 7 export, course import, and study migration (SPEC-012)."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.study_migration_repo import StudyMigrationRepository
from notebooklm_batch_studio.adapters.literature.factory import AdapterLiteratureRuntime
from notebooklm_batch_studio.domain.literature.tracker import AlreadyRunningError, ItemStatus
from notebooklm_batch_studio.domain.study_hierarchy import (
    DEFAULT_LITERATURE_CATEGORY,
    DEFAULT_LITERATURE_SUBFOLDER,
    STUDY_CATEGORIES,
)
from notebooklm_batch_studio.services.literature.jobs import JobRunOptions, LiteratureJobRunner
from notebooklm_batch_studio.services.literature.manager import LiteratureManager
from notebooklm_batch_studio.services.study_migration import migrate_courses_to_study_hierarchy

logger = logging.getLogger(__name__)
literature_router = APIRouter()


class LiteratureAddRequest(BaseModel):
    """Request body for adding APA/DOI/title entries to the literature list.

    Attributes:
        text: Multi-line or paragraph-separated references.
        course_code: Optional course code to link these items to.
        category: Target study category (default `01 Material`).
        subfolder: Target subfolder inside category (default `Literature_Review`).
    """

    text: str = Field(..., min_length=1)
    course_code: str | None = None
    category: str = DEFAULT_LITERATURE_CATEGORY
    subfolder: str = DEFAULT_LITERATURE_SUBFOLDER


class LiteratureProcessRequest(BaseModel):
    """Request body for starting a background literature fetch job.

    Attributes:
        keys: Optional explicit keys to process; None processes pending/review items.
        interactive: Launch visible Chrome and wait for manual CAPTCHA/login.
        identify_only: Only resolve Crossref metadata and APA 7 without downloading PDFs.
        no_browser: Only try open-access HTTP sources.
    """

    keys: list[str] | None = None
    interactive: bool = False
    identify_only: bool = False
    no_browser: bool = False


class LiteratureReidentifyRequest(BaseModel):
    """Request body for replacing an item's input and re-identifying metadata.

    Attributes:
        text: Corrected APA, title, or DOI string.
    """

    text: str = Field(..., min_length=1)


class LiteratureImportCourseRequest(BaseModel):
    """Request body for importing a downloaded PDF into a course folder.

    Attributes:
        course_code: Optional course code override if item was unlinked.
        category: Optional target study category override.
        subfolder: Optional target subfolder override.
    """

    course_code: str | None = None
    category: str | None = None
    subfolder: str | None = None


class StudyMigrateRequest(BaseModel):
    """Request body for migrating legacy courses to `<term>/<subject>/<category>`.

    Attributes:
        dry_run: When True, return planned moves without modifying disk or DB.
    """

    dry_run: bool = False


def _job_runner(request: Request) -> LiteratureJobRunner:
    """Retrieve `LiteratureJobRunner` from FastAPI app state.

    Args:
        request: Incoming HTTP request.

    Returns:
        Configured `LiteratureJobRunner`.
    """
    return request.app.state.literature_jobs  # type: ignore[no-any-return]


def _with_manager(request: Request) -> tuple[Any, LiteratureManager, LiteratureRepository]:
    """Open a short-lived DB session and construct `LiteratureManager`.

    Args:
        request: Incoming HTTP request.

    Returns:
        Tuple of `(session, manager, lit_repo)`.
    """
    cfg = request.app.state.config
    session = request.app.state.session_factory()
    lit_repo = LiteratureRepository(session)
    course_repo = CourseRepository(session)
    manager = LiteratureManager(cfg, lit_repo, course_repo, AdapterLiteratureRuntime(cfg))
    return session, manager, lit_repo


@literature_router.get("/api/literature", tags=["Literature"], operation_id="list_literature")
def list_literature_endpoint(request: Request, course_code: str | None = None) -> dict[str, Any]:
    """List tracked literature items, status counts, and current background job state.

    Args:
        request: HTTP request context.
        course_code: Optional course filter.

    Returns:
        Dictionary with `items`, `counts`, `categories`, `running`, and `job`.
    """
    runner = _job_runner(request)
    current_key, current_stage = runner.live_stage()
    session, manager, lit_repo = _with_manager(request)
    try:
        new_keys = manager.sync_untracked_pdfs()
        if new_keys and not runner.is_running():
            try:
                runner.start(
                    kind="identify",
                    opts=JobRunOptions(keys=new_keys, identify_only=True, no_browser=True),
                )
            except AlreadyRunningError:
                pass
        items = lit_repo.list_items(course_code=course_code)
        counts = Counter(item.status.value for item in items)
        latest = lit_repo.latest_job()
        return {
            "items": [
                manager.serialize_item(item, stage=current_stage if item.key == current_key else "")
                for item in items
            ],
            "counts": {st.value: counts.get(st.value, 0) for st in ItemStatus},
            "categories": list(STUDY_CATEGORIES),
            "scratch_dir": str(request.app.state.config.scratch_dir),
            "unarchived_dir": str(request.app.state.config.literature_dir),
            "running": runner.is_running(),
            "job": latest.__dict__ if latest else None,
        }
    finally:
        session.close()


@literature_router.post("/api/literature/add", tags=["Literature"], operation_id="add_literature")
def add_literature_endpoint(req: LiteratureAddRequest, request: Request) -> dict[str, Any]:
    """Add new APA, title, or DOI entries to the literature queue.

    Args:
        req: Entries and target course/category/subfolder.
        request: HTTP request context.

    Returns:
        Dictionary with count and added keys.
    """
    session, manager, _ = _with_manager(request)
    try:
        added = manager.add_entries(
            req.text,
            course_code=req.course_code,
            category=req.category,
            subfolder=req.subfolder,
        )
        return {"added": len(added), "keys": [item.key for item in added]}
    finally:
        session.close()


@literature_router.post("/api/literature/process", tags=["Literature"], operation_id="process_literature")
def process_literature_endpoint(req: LiteratureProcessRequest, request: Request) -> dict[str, Any]:
    """Start a background literature identification & PDF download batch.

    Args:
        req: Processing options (`interactive`, `identify_only`, `no_browser`, `keys`).
        request: HTTP request context.

    Returns:
        Started job metadata.
    """
    runner = _job_runner(request)
    kind = "identify" if req.identify_only else ("interactive" if req.interactive else "download")
    try:
        job = runner.start(
            kind=kind,
            opts=JobRunOptions(
                keys=req.keys,
                interactive=req.interactive,
                identify_only=req.identify_only,
                no_browser=req.no_browser,
            ),
        )
        return {"job": job.__dict__}
    except AlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@literature_router.post("/api/literature/{key}/retry", tags=["Literature"], operation_id="retry_literature")
def retry_literature_endpoint(key: str, req: LiteratureProcessRequest, request: Request) -> dict[str, Any]:
    """Reset one literature item to pending and launch a fetch job for it.

    Args:
        key: Literature item key.
        req: Processing options (`interactive`, `no_browser`).
        request: HTTP request context.

    Returns:
        Started job metadata.
    """
    session, _, lit_repo = _with_manager(request)
    try:
        item = lit_repo.get_item(key)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Literature item not found: {key}")
        from dataclasses import replace

        lit_repo.upsert_item(replace(item, status=ItemStatus.PENDING, note=""))
    finally:
        session.close()

    runner = _job_runner(request)
    try:
        job = runner.start(
            kind="interactive" if req.interactive else "retry",
            opts=JobRunOptions(
                keys=[key],
                interactive=req.interactive,
                no_browser=req.no_browser,
            ),
        )
        return {"job": job.__dict__}
    except AlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@literature_router.post(
    "/api/literature/{key}/refresh", tags=["Literature"], operation_id="refresh_literature"
)
def refresh_literature_endpoint(key: str, req: LiteratureProcessRequest, request: Request) -> dict[str, Any]:
    """Attempt to upgrade an author-copy PDF to the publisher's version of record.

    Args:
        key: Literature item key.
        req: Processing options (`interactive`, `no_browser`).
        request: HTTP request context.

    Returns:
        Started job metadata.
    """
    session, _, lit_repo = _with_manager(request)
    try:
        if lit_repo.get_item(key) is None:
            raise HTTPException(status_code=404, detail=f"Literature item not found: {key}")
    finally:
        session.close()

    runner = _job_runner(request)
    try:
        job = runner.start(
            kind="refresh",
            opts=JobRunOptions(
                keys=[key],
                refresh_keys=frozenset({key}),
                interactive=req.interactive,
                no_browser=req.no_browser,
            ),
        )
        return {"job": job.__dict__}
    except AlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@literature_router.post(
    "/api/literature/{key}/reidentify", tags=["Literature"], operation_id="reidentify_literature"
)
def reidentify_literature_endpoint(
    key: str, req: LiteratureReidentifyRequest, request: Request
) -> dict[str, Any]:
    """Update an item's input text and re-run Crossref/OpenAlex identification.

    Args:
        key: Existing literature item key.
        req: New input text.
        request: HTTP request context.

    Returns:
        Updated serialized literature item.
    """
    session, manager, _ = _with_manager(request)
    try:
        updated = manager.reidentify_item(key, req.text)
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Literature item not found: {key}")
        return {"item": manager.serialize_item(updated)}
    finally:
        session.close()


@literature_router.post(
    "/api/literature/{key}/import-to-course",
    tags=["Literature"],
    operation_id="import_literature_to_course",
)
def import_literature_to_course_endpoint(
    key: str, req: LiteratureImportCourseRequest, request: Request
) -> dict[str, Any]:
    """Import a downloaded literature PDF into its linked course folder and rescan lectures.

    Args:
        key: Literature item key.
        req: Optional course code override.
        request: HTTP request context.

    Returns:
        Updated serialized literature item.
    """
    session, manager, lit_repo = _with_manager(request)
    try:
        prev = lit_repo.get_item(key)
        prev_code = prev.course_code if prev else None
        saved = manager.import_to_course(
            key,
            course_code=req.course_code,
            category=req.category,
            subfolder=req.subfolder,
        )
        for code in {prev_code, saved.course_code}:
            if not code:
                continue
            course = manager.course_repo.get_course(code)
            if course is not None:
                request.app.state.service.register_course(course.source_dir, custom_code=course.code)
        return {"item": manager.serialize_item(saved)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


@literature_router.post(
    "/api/literature/{key}/unarchive",
    tags=["Literature"],
    operation_id="unarchive_literature",
)
def unarchive_literature_endpoint(key: str, request: Request) -> dict[str, Any]:
    """Move an archived literature PDF back to the unarchived staging folder.

    Args:
        key: Literature item key.
        request: HTTP request context.

    Returns:
        Updated serialized literature item.
    """
    session, manager, lit_repo = _with_manager(request)
    try:
        prev = lit_repo.get_item(key)
        prev_code = prev.course_code if prev else None
        saved = manager.unarchive_item(key)
        if prev_code:
            course = manager.course_repo.get_course(prev_code)
            if course is not None:
                request.app.state.service.register_course(course.source_dir, custom_code=course.code)
        return {"item": manager.serialize_item(saved)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        session.close()


@literature_router.delete("/api/literature/{key}", tags=["Literature"], operation_id="delete_literature")
def delete_literature_endpoint(key: str, request: Request) -> dict[str, Any]:
    """Delete a literature item from the tracker list (PDF on disk is preserved).

    Args:
        key: Literature item key.
        request: HTTP request context.

    Returns:
        Deletion status dictionary.
    """
    session, _, lit_repo = _with_manager(request)
    try:
        deleted = lit_repo.delete_item(key)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Literature item not found: {key}")
        return {"deleted": True, "key": key}
    finally:
        session.close()


@literature_router.get("/api/literature/{key}/pdf", tags=["Literature"], operation_id="get_literature_pdf")
def get_literature_pdf_endpoint(key: str, request: Request) -> FileResponse:
    """Serve the downloaded PDF inline for browser preview.

    Args:
        key: Literature item key.
        request: HTTP request context.

    Returns:
        `FileResponse` with `application/pdf`.
    """
    session, manager, _ = _with_manager(request)
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


@literature_router.get(
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
    session, manager, _ = _with_manager(request)
    try:
        key_list = [k.strip() for k in keys.split(",") if k.strip()] if keys else None
        return manager.export_apa_list(course_code=course_code, keys=key_list)
    finally:
        session.close()


@literature_router.get(
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
    session, manager, _ = _with_manager(request)
    try:
        md = manager.export_report(course_code=course_code)
        return PlainTextResponse(
            md,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="literature_report.md"'},
        )
    finally:
        session.close()


@literature_router.post(
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

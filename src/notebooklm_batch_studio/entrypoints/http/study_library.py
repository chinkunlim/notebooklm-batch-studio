"""HTTP routes for study library scanning, filing, course lifecycle, and learning records (SPEC-014)."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from notebooklm_batch_studio.adapters.db.course_identity_repo import CourseIdentityRepository
from notebooklm_batch_studio.adapters.db.learning_repository import LearningRepository
from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.notes_repository import QANoteRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.path_safety import PathSafetyError
from notebooklm_batch_studio.domain.study_layout import CategoryRole
from notebooklm_batch_studio.services.course_lifecycle import CourseLifecycleService
from notebooklm_batch_studio.services.filing import FilingService, FilingTarget
from notebooklm_batch_studio.services.learning_record import LearningRecordService, RecordRepos
from notebooklm_batch_studio.services.study_library import StudyLibraryService

logger = logging.getLogger(__name__)

study_library_router = APIRouter()


class RegisterCoursesRequest(BaseModel):
    """Body for registering scanned study-library course codes."""

    codes: list[str] = Field(..., description="Course codes to register")
    archive: bool = Field(True, description="Mark registered past courses as archived")


class RegisterFolderRequest(BaseModel):
    """Body for manually registering a non-standard folder under `study/<term>/`."""

    term: str = Field(..., description="Academic term such as 115-1")
    folder: str = Field(..., description="Folder basename under the term")
    course_no: str = Field(..., description="Course number to assign")


class FileItemRequest(BaseModel):
    """Body for moving an unfiled or course file into a course category."""

    path: str = Field(..., description="Absolute path inside scratch/ or a registered course")
    course_code: str = Field(..., description="Destination course code")
    role: str = Field(..., description="Semantic role (materials, handouts, notes, homework, assignments)")
    subfolder: str = Field("", description="Optional subfolder inside the category")


class UnfileItemRequest(BaseModel):
    """Body for moving a course file back into `scratch/unarchived/`."""

    path: str = Field(..., description="Absolute file path inside a registered course directory")


class RenameCourseRequest(BaseModel):
    """Body for previewing or applying a course-code rename."""

    new_code: str = Field(..., description="Replacement course code")
    dry_run: bool = Field(True, description="Preview impact without changing DB or files when True")


def _session(request: Request) -> Any:
    """Open a request-local SQLAlchemy session context manager from `app.state`.

    Args:
        request: Incoming FastAPI request.

    Returns:
        SQLAlchemy session context manager.
    """
    return request.app.state.session_factory()


def _map_error(exc: Exception) -> HTTPException:
    """Convert domain and validation exceptions into structured HTTP error statuses.

    Args:
        exc: Raised domain/filesystem exception.

    Returns:
        Configured `HTTPException`.
    """
    if isinstance(exc, (CourseNotFoundError, FileNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PathSafetyError):
        return HTTPException(status_code=400, detail=str(exc))
    msg = str(exc)
    if "找不到課程" in msg or "not found" in msg.lower():
        return HTTPException(status_code=404, detail=msg)
    if "已存在" in msg or "執行中" in msg:
        return HTTPException(status_code=409, detail=msg)
    return HTTPException(status_code=400, detail=msg)


def _record_service(cfg: Any, db: Any) -> LearningRecordService:
    """Build `LearningRecordService` bound to `cfg` and DB session `db`.

    Args:
        cfg: Application configuration.
        db: Active SQLAlchemy session.

    Returns:
        Configured `LearningRecordService`.
    """
    repos = RecordRepos(
        queue_repo=QueueRepository(db),
        study_repo=StudyRepository(db),
        learning_repo=LearningRepository(db),
        qa_repo=QANoteRepository(db),
        literature_repo=LiteratureRepository(db),
    )
    return LearningRecordService(cfg, CourseRepository(db), repos)


@study_library_router.get("/api/study/layout", tags=["StudyLibrary"], operation_id="get_study_layout")
def get_study_layout(request: Request) -> dict[str, Any]:
    """Return configured study folder category names, aliases, and semantic roles.

    Args:
        request: Incoming HTTP request.

    Returns:
        Dictionary with `names`, `aliases`, and `roles`.
    """
    layout = request.app.state.config.study_layout
    return {
        "names": {r.value: layout.names[r] for r in CategoryRole},
        "aliases": {r.value: list(layout.aliases.get(r, ())) for r in CategoryRole},
        "roles": [r.value for r in CategoryRole],
    }


@study_library_router.get("/api/study/library", tags=["StudyLibrary"], operation_id="scan_study_library")
def scan_study_library(request: Request) -> dict[str, Any]:
    """Scan `study/<term>/` for registered courses, unregistered candidates, and loose folders.

    Args:
        request: Incoming HTTP request.

    Returns:
        Dictionary with sorted `terms` list.
    """
    cfg = request.app.state.config
    with _session(request) as db:
        terms = StudyLibraryService(cfg, CourseRepository(db)).scan()
    return {"terms": [asdict(t) for t in terms]}


@study_library_router.post(
    "/api/study/library/register", tags=["StudyLibrary"], operation_id="register_past_courses"
)
def register_past_courses(body: RegisterCoursesRequest, request: Request) -> dict[str, Any]:
    """Register discovered study-library courses in record-only mode without queueing jobs.

    Args:
        body: Selected course codes and archive flag.
        request: Incoming HTTP request.

    Returns:
        Dictionary with per-code `results`.
    """
    cfg = request.app.state.config
    try:
        with _session(request) as db:
            results = StudyLibraryService(cfg, CourseRepository(db)).register(
                body.codes, archive=body.archive
            )
        return {"results": results}
    except (ValueError, PathSafetyError) as exc:
        raise _map_error(exc) from exc


@study_library_router.post(
    "/api/study/library/register-folder", tags=["StudyLibrary"], operation_id="register_study_folder"
)
def register_study_folder(body: RegisterFolderRequest, request: Request) -> dict[str, Any]:
    """Register a non-standard folder inside `study/<term>/` with an explicit course number.

    Args:
        body: Term, folder name, and course number payload.
        request: Incoming HTTP request.

    Returns:
        Registered course metadata dictionary.
    """
    cfg = request.app.state.config
    try:
        with _session(request) as db:
            return StudyLibraryService(cfg, CourseRepository(db)).register_folder(
                body.term, body.folder, body.course_no
            )
    except (FileNotFoundError, ValueError, PathSafetyError) as exc:
        raise _map_error(exc) from exc


@study_library_router.get("/api/study/unfiled", tags=["StudyLibrary"], operation_id="list_unfiled")
def list_unfiled(request: Request, kind: str | None = None) -> dict[str, Any]:
    """List files waiting inside `DATA_DIR/scratch/`, optionally filtered by scratch kind.

    Args:
        request: Incoming HTTP request.
        kind: Optional scratch subdirectory filter.

    Returns:
        Dictionary with `items` metadata list.
    """
    cfg = request.app.state.config
    try:
        with _session(request) as db:
            items = FilingService(cfg, CourseRepository(db)).list_unfiled(kind)
        return {"items": items}
    except ValueError as exc:
        raise _map_error(exc) from exc


@study_library_router.post("/api/study/file", tags=["StudyLibrary"], operation_id="file_study_item")
def file_study_item(body: FileItemRequest, request: Request) -> dict[str, str]:
    """Move a scratch or course file into the requested course category/subfolder.

    Args:
        body: Source path and filing destination metadata.
        request: Incoming HTTP request.

    Returns:
        Dictionary with destination file path `dest`.
    """
    cfg = request.app.state.config
    try:
        role = CategoryRole(body.role)
        with _session(request) as db:
            dest = FilingService(cfg, CourseRepository(db)).file(
                Path(body.path), FilingTarget(body.course_code, role, body.subfolder)
            )
        return {"dest": str(dest)}
    except (CourseNotFoundError, FileNotFoundError, PathSafetyError, ValueError) as exc:
        raise _map_error(exc) from exc


@study_library_router.post("/api/study/unfile", tags=["StudyLibrary"], operation_id="unfile_study_item")
def unfile_study_item(body: UnfileItemRequest, request: Request) -> dict[str, str]:
    """Move a file out of a registered course directory into `scratch/unarchived/<code>/`.

    Args:
        body: Source course file path payload.
        request: Incoming HTTP request.

    Returns:
        Dictionary with destination scratch file path `dest`.
    """
    cfg = request.app.state.config
    try:
        with _session(request) as db:
            dest = FilingService(cfg, CourseRepository(db)).unfile(Path(body.path))
        return {"dest": str(dest)}
    except (FileNotFoundError, PathSafetyError, ValueError) as exc:
        raise _map_error(exc) from exc


@study_library_router.post("/api/courses/{code}/archive", tags=["Courses"], operation_id="archive_course")
def archive_course(code: str, request: Request) -> dict[str, Any]:
    """Archive an active course so it drops from queue execution, Today, and due reviews.

    Args:
        code: Course identifier.
        request: Incoming HTTP request.

    Returns:
        Status summary dictionary.
    """
    cfg = request.app.state.config
    try:
        with _session(request) as db:
            svc = CourseLifecycleService(
                CourseRepository(db), QueueRepository(db), CourseIdentityRepository(db), cfg
            )
            return svc.archive(code)
    except ValueError as exc:
        raise _map_error(exc) from exc


@study_library_router.post("/api/courses/{code}/restore", tags=["Courses"], operation_id="restore_course")
def restore_course(code: str, request: Request) -> dict[str, Any]:
    """Restore an archived course back to active status.

    Args:
        code: Course identifier.
        request: Incoming HTTP request.

    Returns:
        Status summary dictionary.
    """
    cfg = request.app.state.config
    try:
        with _session(request) as db:
            svc = CourseLifecycleService(
                CourseRepository(db), QueueRepository(db), CourseIdentityRepository(db), cfg
            )
            return svc.restore(code)
    except ValueError as exc:
        raise _map_error(exc) from exc


@study_library_router.post("/api/courses/{code}/rename", tags=["Courses"], operation_id="rename_course_code")
def rename_course_code(code: str, body: RenameCourseRequest, request: Request) -> dict[str, Any]:
    """Preview (default `dry_run=True`) or apply a transactional course-code rename.

    Args:
        code: Existing course identifier.
        body: Replacement code and `dry_run` flag.
        request: Incoming HTTP request.

    Returns:
        Affected row and file counts dictionary.
    """
    cfg = request.app.state.config
    try:
        with _session(request) as db:
            svc = CourseLifecycleService(
                CourseRepository(db), QueueRepository(db), CourseIdentityRepository(db), cfg
            )
            return svc.rename(code, body.new_code, dry_run=body.dry_run)
    except (PathSafetyError, ValueError) as exc:
        raise _map_error(exc) from exc


@study_library_router.get("/api/study/record", tags=["StudyLibrary"], operation_id="get_learning_record")
def get_learning_record(request: Request, term: str | None = None) -> dict[str, Any]:
    """Build cross-term learning record views including archived and unregistered folders.

    Args:
        request: Incoming HTTP request.
        term: Optional semester filter.

    Returns:
        Dictionary with sorted `terms` entries and active `layout` folder names.
    """
    cfg = request.app.state.config
    with _session(request) as db:
        terms = _record_service(cfg, db).build(term=term)
    return {
        "terms": [asdict(t) for t in terms],
        "layout": {role.value: cfg.study_layout.names[role] for role in CategoryRole},
    }


@study_library_router.get(
    "/api/study/record/export", tags=["StudyLibrary"], operation_id="export_learning_record"
)
def export_learning_record(request: Request, term: str | None = None, format: str = "md") -> Response:
    """Export the cross-term learning record as downloadable Markdown or PDF.

    Args:
        request: Incoming HTTP request.
        term: Optional semester filter.
        format: Output format (`md` or `pdf`).

    Returns:
        Streaming download response (`text/markdown` or `application/pdf`).
    """
    fmt = format.strip().lower()
    if fmt not in {"md", "pdf"}:
        raise HTTPException(status_code=400, detail="format 僅支援 md 或 pdf")
    cfg = request.app.state.config
    with _session(request) as db:
        svc = _record_service(cfg, db)
        if fmt == "md":
            md = svc.export_markdown(term=term)
            return Response(
                content=md.encode("utf-8"),
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="learning-record.md"'},
            )
        cfg.tmp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=cfg.tmp_dir, prefix="learning-record-", suffix=".pdf", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            svc.export_pdf(term=term, out=tmp_path)
            pdf_bytes = tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="learning-record.pdf"'},
        )

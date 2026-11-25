"""HTTP routes for textbook splitting and moving misfiled chapters out of `02 Handouts` (SPEC-018)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.pdf_textbook import PypdfTextbookTools
from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import CourseStatus
from notebooklm_batch_studio.domain.path_safety import PathSafetyError
from notebooklm_batch_studio.services.course_folders import list_category_subfolders
from notebooklm_batch_studio.services.course_parser import ignored_handout_rows
from notebooklm_batch_studio.services.textbook_split import TextbookService

logger = logging.getLogger(__name__)

textbooks_router = APIRouter(tags=["Textbooks"])


class SplitTextbookRequest(BaseModel):
    """Body for previewing or splitting one textbook PDF."""

    relative_path: str = Field(..., description="Course-relative path from GET /textbooks")
    dry_run: bool = Field(True, description="Preview only when True")


class RelocateHandoutsRequest(BaseModel):
    """Body for moving chapter PDFs from 02 Handouts into 01 Materials/<book_folder>/."""

    book_folder: str = Field(..., description="Textbook folder name inside 01 Materials")
    dry_run: bool = Field(True, description="Preview only when True")


def _run(request: Request, fn: Callable[[TextbookService], Any]) -> Any:
    """Run a TextbookService call on a request session, mapping errors to HTTP statuses.

    Args:
        request: Incoming HTTP request.
        fn: Callable receiving the service.

    Returns:
        The callable's result.

    Raises:
        HTTPException: 404 for unknown courses, 422 for invalid paths or textbooks.
    """
    try:
        with request.app.state.session_factory() as db:
            return fn(TextbookService(request.app.state.config, CourseRepository(db), PypdfTextbookTools()))
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@textbooks_router.get("/api/courses/{code}/textbooks", operation_id="list_textbooks")
def list_textbooks(code: str, request: Request) -> dict[str, Any]:
    """List top-level PDFs in the course's 01 Materials folders.

    Args:
        code: Course identifier.
        request: Incoming HTTP request.

    Returns:
        `{"textbooks": [...]}`.
    """
    return {"textbooks": _run(request, lambda svc: svc.list_textbooks(code))}


@textbooks_router.post("/api/courses/{code}/textbooks/split", operation_id="split_textbook")
def split_textbook(code: str, body: SplitTextbookRequest, request: Request) -> dict[str, Any]:
    """Preview (default) or write chapter PDFs into `01 Materials/<book>/`.

    Args:
        code: Course identifier.
        body: Textbook path and dry-run flag.
        request: Incoming HTTP request.

    Returns:
        Chapter plan or result.
    """
    result: dict[str, Any] = _run(
        request, lambda svc: svc.split_textbook(code, body.relative_path, body.dry_run)
    )
    return result


@textbooks_router.post("/api/courses/{code}/textbooks/relocate-handouts", operation_id="relocate_handouts")
def relocate_handouts(code: str, body: RelocateHandoutsRequest, request: Request) -> dict[str, Any]:
    """Preview (default) or move lecture PDFs from `02 Handouts` into a textbook folder.

    Args:
        code: Course identifier.
        body: Book folder name and dry-run flag.
        request: Incoming HTTP request.

    Returns:
        Move plan or result.
    """
    result: dict[str, Any] = _run(
        request, lambda svc: svc.relocate_handouts(code, body.book_folder, body.dry_run)
    )
    return result


@textbooks_router.get("/api/courses/{code}/subfolders", operation_id="list_course_subfolders")
def list_course_subfolders(code: str, category: str, request: Request) -> dict[str, Any]:
    """List existing subfolders of one course category for the web folder pickers.

    Args:
        code: Course identifier.
        category: Category folder name such as `01 Materials`.
        request: Incoming HTTP request.

    Returns:
        `{"subfolders": [...]}`.

    Raises:
        HTTPException: 404 for unknown courses, 400 for unsafe category names.
    """
    try:
        with request.app.state.session_factory() as db:
            return {"subfolders": list_category_subfolders(CourseRepository(db), code, category)}
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PathSafetyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@textbooks_router.get("/api/textbooks/pending", operation_id="list_pending_textbooks")
def list_pending_textbooks(request: Request) -> dict[str, Any]:
    """List unsplit textbooks in active courses' 01 Materials folders (Refs: SPEC-020).

    Args:
        request: Incoming HTTP request.

    Returns:
        `{"pending": [...], "ignored_handouts": [...]}`: chapter counts or why a book cannot be split,
        and handouts that are not lectures because the course uses textbook chapters (SPEC-025 R4a).
    """

    def scan(svc: TextbookService) -> dict[str, Any]:
        """Collect pending textbooks and ignored handouts for every active course.

        Args:
            svc: Textbook service bound to the request session.

        Returns:
            `{"pending": [...], "ignored_handouts": [...]}`.
        """
        courses = svc.course_repo.list_courses(status=CourseStatus.ACTIVE)  # type: ignore[attr-defined]
        return {
            "pending": svc.pending_textbooks([c.code for c in courses]),
            "ignored_handouts": ignored_handout_rows(courses, svc.config.study_layout),  # SPEC-025 R4a
        }

    result: dict[str, Any] = _run(request, scan)
    return result

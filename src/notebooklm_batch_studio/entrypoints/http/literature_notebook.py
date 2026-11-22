"""FastAPI routes for Gemini Literature Notebook sync, search Q&A, and Literature Reviews."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.literature.factory import AdapterLiteratureRuntime
from notebooklm_batch_studio.services.literature.manager import LiteratureManager
from notebooklm_batch_studio.services.literature.notebook_service import LiteratureNotebookService

logger = logging.getLogger(__name__)
literature_notebook_router = APIRouter()
_review_task: asyncio.Task[Any] | None = None
_review_message: str = ""


class LiteratureAskRequest(BaseModel):
    """Request body for querying the Gemini Literature Notebook.

    Attributes:
        question: Natural language query across all uploaded papers.
    """

    question: str = Field(..., min_length=1)


class LiteratureReviewRequest(BaseModel):
    """Request body for generating or regenerating a single-paper Literature Review.

    Attributes:
        force: Regenerate even if a review already exists.
    """

    force: bool = False


def _nb_service(request: Request) -> tuple[Any, LiteratureNotebookService]:
    """Open a DB session and construct `LiteratureNotebookService`.

    Args:
        request: Incoming HTTP request.

    Returns:
        Tuple of `(session, LiteratureNotebookService)`.
    """
    cfg = request.app.state.config
    session = request.app.state.session_factory()
    manager = LiteratureManager(
        cfg,
        LiteratureRepository(session),
        CourseRepository(session),
        AdapterLiteratureRuntime(cfg),
    )
    nb_svc = LiteratureNotebookService(
        notebooklm=request.app.state.service.notebooklm_client,
        manager=manager,
        prefs=request.app.state.preferences,
    )
    return session, nb_svc


@literature_notebook_router.get(
    "/api/literature/notebook", tags=["Literature"], operation_id="get_literature_notebook"
)
def get_literature_notebook_endpoint(request: Request) -> dict[str, Any]:
    """Return Gemini Literature Notebook status, URL, and sync/review counts.

    Args:
        request: HTTP request context.

    Returns:
        Status dictionary.
    """
    session, svc = _nb_service(request)
    try:
        running = _review_task is not None and not _review_task.done()
        return {**svc.get_status(), "review_running": running, "review_message": _review_message}
    finally:
        session.close()


@literature_notebook_router.post(
    "/api/literature/notebook/sync", tags=["Literature"], operation_id="sync_literature_notebook"
)
async def sync_literature_notebook_endpoint(request: Request) -> dict[str, Any]:
    """Create (or reuse) the Literature Library Gemini Notebook and upload missing PDFs.

    Args:
        request: HTTP request context.

    Returns:
        Updated notebook status and uploaded count.
    """
    session, svc = _nb_service(request)
    try:
        return await svc.sync_pdfs()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        session.close()


@literature_notebook_router.post(
    "/api/literature/notebook/ask", tags=["Literature"], operation_id="ask_literature_notebook"
)
async def ask_literature_notebook_endpoint(req: LiteratureAskRequest, request: Request) -> dict[str, Any]:
    """Query the Gemini Literature Notebook across all uploaded papers.

    Args:
        req: Question payload.
        request: HTTP request context.

    Returns:
        Dictionary with `notebook_id`, `answer`, and `references`.
    """
    session, svc = _nb_service(request)
    try:
        return await svc.query(req.question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        session.close()


@literature_notebook_router.post(
    "/api/literature/{key}/review", tags=["Literature"], operation_id="generate_literature_review"
)
async def generate_literature_review_endpoint(
    key: str, req: LiteratureReviewRequest, request: Request
) -> dict[str, Any]:
    """Generate a Western-university-format Literature Review for one paper.

    Args:
        key: Literature item key.
        req: Generation options (`force`).
        request: HTTP request context.

    Returns:
        Updated serialized literature item including `review_markdown`.
    """
    session, svc = _nb_service(request)
    try:
        updated = await svc.generate_review(key, force=req.force)
        return {"item": svc.manager.serialize_item(updated)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        session.close()


@literature_notebook_router.post(
    "/api/literature/reviews/batch", tags=["Literature"], operation_id="batch_literature_reviews"
)
async def batch_literature_reviews_endpoint(request: Request) -> dict[str, Any]:
    """Start background generation of missing Literature Reviews (waits & resumes on quota).

    Args:
        request: HTTP request context.

    Returns:
        Dictionary indicating batch task started state.
    """
    global _review_task, _review_message
    if _review_task is not None and not _review_task.done():
        return {"started": False, "review_running": True, "review_message": _review_message}

    async def _run_batch() -> None:
        """Execute batch Literature Review generation in the background."""
        global _review_message
        session, svc = _nb_service(request)
        try:

            def _on_msg(msg: str) -> None:
                """Record latest progress status message.

                Args:
                    msg: Status message text.
                """
                global _review_message
                _review_message = msg

            res = await svc.generate_missing_reviews(progress_cb=_on_msg)
            _review_message = f"已完成 {len(res['generated'])} 篇 Literature Review"
        except Exception as exc:
            _review_message = f"批次生成失敗：{exc}"
        finally:
            session.close()

    _review_message = "準備批次生成 Literature Review…"
    _review_task = asyncio.create_task(_run_batch())
    return {"started": True, "review_running": True, "review_message": _review_message}

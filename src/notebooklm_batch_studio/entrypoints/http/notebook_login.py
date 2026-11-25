"""FastAPI route that opens real Chrome for Gemini Notebook sign-in (Refs: SPEC-022)."""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from notebooklm_batch_studio.adapters.notebooklm.chrome_login import build_notebook_login_service
from notebooklm_batch_studio.services.notebook_login import LoginInProgressError, NotebookLoginService

logger = logging.getLogger(__name__)
notebook_login_router = APIRouter(tags=["System"])


class NotebookLoginRequest(BaseModel):
    """Request body for the Gemini Notebook Chrome sign-in.

    Attributes:
        timeout_seconds: Longest wait for the user to finish signing in.
    """

    timeout_seconds: int = Field(default=300, ge=10, le=1800)


def _service(request: Request) -> NotebookLoginService:
    """Return the app-wide sign-in service (one per app, so its lock covers every request).

    Args:
        request: Incoming HTTP request.

    Returns:
        `NotebookLoginService`.
    """
    existing = getattr(request.app.state, "notebook_login", None)
    if existing is None:
        existing = build_notebook_login_service(request.app.state.config)
        request.app.state.notebook_login = existing
    return cast(NotebookLoginService, existing)


@notebook_login_router.post("/api/notebooklm/login", operation_id="notebooklm_login")
def notebooklm_login_route(body: NotebookLoginRequest, request: Request) -> dict[str, Any]:
    """Open real Chrome so the user signs in to Gemini Notebook; keep the session only if it works.

    Args:
        body: Timeout options.
        request: Incoming HTTP request.

    Returns:
        `{"status": "signed_in" | "timeout" | "not_verified", "message": str}`.

    Raises:
        HTTPException: 409 while another sign-in is waiting.
    """
    try:
        return _service(request).login(body.timeout_seconds)
    except LoginInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

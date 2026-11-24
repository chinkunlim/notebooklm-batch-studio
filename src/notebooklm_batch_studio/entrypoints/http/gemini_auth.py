"""FastAPI routes for Gemini Web interactive login and session status (Refs: ISSUE-053)."""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from notebooklm_batch_studio.adapters.note_driver_factory import build_gemini_auth_service
from notebooklm_batch_studio.services.notes.gemini_auth_service import GeminiAuthService

logger = logging.getLogger(__name__)
gemini_auth_router = APIRouter(prefix="/api/notes/gemini", tags=["notes"])


class GeminiLoginRequest(BaseModel):
    """Request body for starting an interactive real-Chrome Gemini login window.

    Attributes:
        timeout_seconds: Maximum wait time for the user to finish signing in.
    """

    timeout_seconds: int = Field(default=300, ge=10, le=1800)


class GeminiLogoutRequest(BaseModel):
    """Request body for clearing the persisted Gemini Web session.

    Attributes:
        confirm: Must be True to delete local profile and `storage_state.json`.
    """

    confirm: bool = False


class GeminiRetentionRequest(BaseModel):
    """Request body for updating local cookie retention policy.

    Attributes:
        retention_days: Retention days (0 means follow Google expiry).
        confirm: Must be True to persist the retention change.
    """

    retention_days: int = Field(..., ge=0, le=3650)
    confirm: bool = False


def _auth_service(request: Request) -> GeminiAuthService:
    """Retrieve or lazily construct `GeminiAuthService` from app state.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Configured `GeminiAuthService`.
    """
    existing = getattr(request.app.state, "gemini_auth", None)
    if existing is not None:
        return cast(GeminiAuthService, existing)
    svc = build_gemini_auth_service(request.app.state.config)
    request.app.state.gemini_auth = svc
    return svc


@gemini_auth_router.get("/auth-status")
def get_gemini_auth_status(request: Request, live_check: bool = False) -> dict[str, Any]:
    """Return current Gemini Web login status and cookie metadata.

    Args:
        request: Incoming HTTP request.
        live_check: Whether to perform an active HTTP probe against Gemini.

    Returns:
        Authentication status dictionary.
    """
    return _auth_service(request).check_auth_status(live_check=live_check)


@gemini_auth_router.post("/login")
def start_gemini_login(body: GeminiLoginRequest, request: Request) -> dict[str, Any]:
    """Open real Chrome for manual Google/Gemini sign-in and save session state.

    Args:
        body: Login timeout options.
        request: Incoming HTTP request.

    Returns:
        Login outcome dictionary with `success`, `logged_in`, and `message`.
    """
    return _auth_service(request).login_interactive(timeout_seconds=body.timeout_seconds)


@gemini_auth_router.post("/logout")
def logout_gemini_session(body: GeminiLogoutRequest, request: Request) -> dict[str, Any]:
    """Clear the persisted Gemini Chrome profile and `storage_state.json`.

    Args:
        body: Explicit confirmation flag.
        request: Incoming HTTP request.

    Returns:
        Logout result dictionary.
    """
    auth = _auth_service(request)
    if not body.confirm:
        status = auth.check_auth_status(live_check=False)
        return {
            "success": False,
            "logged_in": bool(status.get("logged_in", False)),
            "message": "請傳入 confirm: true 以確認登出並清除本機 Gemini 憑證。",
        }
    return auth.logout()


@gemini_auth_router.post("/retention")
def set_gemini_retention(body: GeminiRetentionRequest, request: Request) -> dict[str, Any]:
    """Configure local retention days for saved Gemini Web cookies.

    Args:
        body: Retention days and explicit confirmation flag.
        request: Incoming HTTP request.

    Returns:
        Confirmation and saved retention dictionary.
    """
    if not body.confirm:
        return {
            "success": False,
            "message": "請傳入 confirm: true 以確認更新憑證保留期限。",
        }
    return _auth_service(request).set_retention_days(body.retention_days)

"""HTTP routes for web preferences recorded on this computer (ADR-009): read, save and reset."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from notebooklm_batch_studio.services.preferences_service import PreferencesService

preferences_router = APIRouter(prefix="/api/preferences", tags=["Preferences"])


class PreferencesIn(BaseModel):
    """Preference changes.

    Attributes:
        values: Key to new value; null deletes the key.
    """

    values: dict[str, str | None] = Field(default_factory=dict)


class ResetIn(BaseModel):
    """Reset request.

    Attributes:
        keep: Keys to keep (for example the user's own palettes).
    """

    keep: list[str] = Field(default_factory=list)


def _prefs(request: Request) -> PreferencesService:
    """Get the preferences service from the app.

    Args:
        request: Incoming request.

    Returns:
        PreferencesService.
    """
    service: PreferencesService = request.app.state.preferences
    return service


@preferences_router.get("", operation_id="get_ui_preferences")
def get_preferences(request: Request) -> dict[str, dict[str, str]]:
    """Return every remembered preference.

    Args:
        request: Incoming request.

    Returns:
        {"values": {key: value}}.
    """
    return {"values": _prefs(request).get_all()}


@preferences_router.put("", operation_id="set_ui_preferences")
def put_preferences(req: PreferencesIn, request: Request) -> dict[str, dict[str, str]]:
    """Save some preferences and delete others (null deletes).

    Args:
        req: Changes.
        request: Incoming request.

    Returns:
        {"values": {key: value}} after the change.

    Raises:
        HTTPException: 400 when a key or value is invalid.
    """
    try:
        return {"values": _prefs(request).update(req.values)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@preferences_router.post("/reset", operation_id="reset_ui_preferences")
def reset_preferences(req: ResetIn, request: Request) -> dict[str, dict[str, str]]:
    """Delete every preference except the listed keys.

    Args:
        req: Keys to keep.
        request: Incoming request.

    Returns:
        {"values": {key: value}} after the reset.
    """
    return {"values": _prefs(request).reset(req.keep)}

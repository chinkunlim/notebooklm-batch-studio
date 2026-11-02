"""HTTP routes for downloaded Google Fonts (ADR-009): list, download, serve offline and delete."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from notebooklm_batch_studio.domain.exceptions import FontDownloadError
from notebooklm_batch_studio.services.font_service import FontService

fonts_router = APIRouter(prefix="/api/fonts", tags=["Fonts"])


class FontIn(BaseModel):
    """A Google Fonts family to download.

    Attributes:
        family: Family name exactly as on fonts.google.com, e.g. "LXGW WenKai TC".
    """

    family: str = Field(..., min_length=1, max_length=60)


def _fonts(request: Request) -> FontService:
    """Get the font service from the app.

    Args:
        request: Incoming request.

    Returns:
        FontService.
    """
    service: FontService = request.app.state.fonts
    return service


@fonts_router.get("", operation_id="list_fonts")
def list_fonts(request: Request) -> dict[str, list[dict[str, Any]]]:
    """List the downloaded fonts.

    Args:
        request: Incoming request.

    Returns:
        {"fonts": [...]}.
    """
    return {"fonts": _fonts(request).list_fonts()}


@fonts_router.post("", operation_id="install_google_font")
def install_font(req: FontIn, request: Request) -> dict[str, Any]:
    """Download a Google Fonts family to this computer.

    Args:
        req: Family name.
        request: Incoming request.

    Returns:
        The font's description.

    Raises:
        HTTPException: 400 for a bad name, 502 when the download fails.
    """
    try:
        return _fonts(request).install(req.family)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FontDownloadError as exc:
        raise HTTPException(
            status_code=502, detail=f"下載失敗：{exc}（請確認名稱和 fonts.google.com 上一樣，且電腦有連網）"
        ) from exc


@fonts_router.delete("/{slug}", operation_id="delete_font")
def delete_font(slug: str, request: Request) -> dict[str, bool]:
    """Delete a downloaded font.

    Args:
        slug: Font folder name.
        request: Incoming request.

    Returns:
        {"deleted": bool}.

    Raises:
        HTTPException: 400 for a bad name.
    """
    try:
        return {"deleted": _fonts(request).delete(slug)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@fonts_router.get("/{slug}/{name}", operation_id="get_font_file", include_in_schema=False)
def font_file(slug: str, name: str, request: Request) -> FileResponse:
    """Serve one file of a downloaded font (font.css or a woff2 file).

    Args:
        slug: Font folder name.
        name: File name.
        request: Incoming request.

    Returns:
        The file.

    Raises:
        HTTPException: 404 when it is not a servable font file.
    """
    try:
        path = _fonts(request).file_path(slug, name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    media = "text/css" if name.endswith(".css") else "font/woff2"
    return FileResponse(path, media_type=media, headers={"Cache-Control": "max-age=86400"})

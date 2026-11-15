"""FastAPI routes for reverse-importing existing Gemini Notebooks and downloading all files locally."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from notebooklm_batch_studio.entrypoints.schemas import DownloadAllLocalRequest, ReverseImportRequest
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.reverse_import import ReverseImportOptions, ReverseImportService

reverse_import_router = APIRouter(tags=["Remote Import"])


def _build_reverse_import_service(request: Request) -> ReverseImportService:
    """Construct ReverseImportService from FastAPI app.state.

    Args:
        request: Incoming HTTP request context.

    Returns:
        Configured ReverseImportService instance.
    """
    svc: BatchStudioService = request.app.state.service
    return ReverseImportService(
        notebooklm_client=svc.notebooklm_client,
        course_repo=svc.course_repo,
        queue_repo=svc.queue_repo,
        output_base_dir=request.app.state.config.output_dir,
    )


@reverse_import_router.get("/api/remote-notebooks", operation_id="list_remote_notebooks")
async def list_remote_notebooks_endpoint(request: Request) -> dict[str, Any]:
    """List remote Gemini Notebooks and indicate which are already linked locally.

    Args:
        request: Incoming HTTP request context.

    Returns:
        Dictionary containing `notebooks` list.
    """
    svc = _build_reverse_import_service(request)
    try:
        return {"notebooks": await svc.list_remote_notebooks()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list remote notebooks: {exc}") from exc


@reverse_import_router.get(
    "/api/remote-notebooks/{notebook_id}/preview", operation_id="preview_remote_notebook"
)
async def preview_remote_notebook_endpoint(notebook_id: str, request: Request) -> dict[str, Any]:
    """Preview remote sources and artifacts inside a Gemini Notebook before importing.

    Args:
        notebook_id: Remote Gemini Notebook identifier.
        request: Incoming HTTP request context.

    Returns:
        Dictionary with `notebook`, `sources`, and `artifacts`.
    """
    svc = _build_reverse_import_service(request)
    try:
        return await svc.preview_remote_notebook(notebook_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to preview remote notebook: {exc}") from exc


@reverse_import_router.post(
    "/api/remote-notebooks/{notebook_id}/import", operation_id="import_remote_notebook"
)
async def import_remote_notebook_endpoint(
    notebook_id: str, payload: ReverseImportRequest, request: Request
) -> dict[str, Any]:
    """Reverse-import an existing remote Gemini Notebook as a local course and download files.

    Args:
        notebook_id: Remote Gemini Notebook identifier.
        payload: Import options (optional course code/name, whether to download sources/artifacts).
        request: Incoming HTTP request context.

    Returns:
        Summary of imported course, downloaded sources, and synced artifacts.
    """
    svc = _build_reverse_import_service(request)
    opts = ReverseImportOptions(
        notebook_id=notebook_id,
        course_code=payload.course_code,
        course_name=payload.course_name,
        language=payload.language,
        download_sources=payload.download_sources,
        download_artifacts=payload.download_artifacts,
        source_ids=payload.source_ids,
        artifact_ids=payload.artifact_ids,
    )
    try:
        return await svc.import_remote_notebook(opts)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Reverse import failed: {exc}") from exc


@reverse_import_router.post("/api/courses/{code}/download-all", operation_id="download_course_files_locally")
async def download_course_files_endpoint(
    code: str, payload: DownloadAllLocalRequest, request: Request
) -> dict[str, Any]:
    """Download all remote sources and artifacts of a linked course to DATA_DIR.

    Args:
        code: Existing local course code.
        payload: Flags controlling whether to download sources and/or artifacts.
        request: Incoming HTTP request context.

    Returns:
        Summary dictionary with downloaded counts and local folder paths.
    """
    svc = _build_reverse_import_service(request)
    try:
        return await svc.download_course_files_locally(
            code, include_sources=payload.include_sources, include_artifacts=payload.include_artifacts
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Download failed: {exc}") from exc

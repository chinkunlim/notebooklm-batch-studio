"""Registers the literature (SPEC-012) and note-studio (ADR-012) MCP tool groups.

Split out of `mcp_server.py` so the core server builder stays small. Both groups need a
session factory and course-folder lookups, which this module wires up.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import sessionmaker

from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine
from notebooklm_batch_studio.adapters.literature.factory import AdapterLiteratureRuntime
from notebooklm_batch_studio.adapters.locks import RunLock
from notebooklm_batch_studio.adapters.note_driver_factory import (
    build_gemini_auth_service,
    build_note_driver_factory,
    build_note_upload_fn,
)
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.entrypoints.mcp_gemini_auth import register_gemini_auth_tools
from notebooklm_batch_studio.entrypoints.mcp_literature import LiteratureToolDeps, register_literature_tools
from notebooklm_batch_studio.entrypoints.mcp_literature_notebook import register_literature_notebook_tools
from notebooklm_batch_studio.entrypoints.mcp_maintenance import register_maintenance_tools
from notebooklm_batch_studio.entrypoints.mcp_notes import register_note_pipeline_tools
from notebooklm_batch_studio.entrypoints.mcp_study_library import register_study_library_tools
from notebooklm_batch_studio.entrypoints.mcp_textbooks import register_textbook_tools
from notebooklm_batch_studio.services.literature.jobs import LiteratureJobRunner
from notebooklm_batch_studio.services.literature.manager import LiteratureManager
from notebooklm_batch_studio.services.notes.note_pipeline_service import NotePipelineService

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)


def course_dir_resolver(session_factory: Any, attr: str) -> Callable[[str], Path | None]:
    """Build a `course_key -> folder` lookup for one course-record attribute.

    Args:
        session_factory: SQLAlchemy session factory.
        attr: Course record attribute, `study_dir` or `source_dir`.

    Returns:
        Callable returning the folder path, or None when the course or folder is not registered.
    """

    def _resolve(course_key: str) -> Path | None:
        """Look up the folder for `course_key`.

        Args:
            course_key: Course code / identifier.

        Returns:
            Folder path or None.
        """
        with session_factory() as session:
            course = CourseRepository(session).get_course(course_key)
            value = getattr(course, attr, None) if course else None
        return Path(value) if value else None

    return _resolve


def _literature_runner(cfg: AppConfig, session_factory: Any) -> LiteratureJobRunner:
    """Create a literature job runner whose jobs each open their own session.

    Args:
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.

    Returns:
        New `LiteratureJobRunner`.
    """

    @contextmanager
    def _lit_scope() -> Iterator[LiteratureManager]:
        """Yield a scoped `LiteratureManager`.

        Yields:
            Manager bound to a fresh session.
        """
        with session_factory() as session:
            yield LiteratureManager(
                cfg, LiteratureRepository(session), CourseRepository(session), AdapterLiteratureRuntime(cfg)
            )

    return LiteratureJobRunner(_lit_scope, lock_path=cfg.literature_job_lock_path, lock_factory=RunLock)


def _note_service(cfg: AppConfig, session_factory: Any, override: Any) -> NotePipelineService:
    """Return the injected note pipeline service or build one with course-folder lookups.

    Args:
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.
        override: Optional pre-configured `NotePipelineService`.

    Returns:
        Note pipeline service.
    """
    if override is not None:
        return override  # type: ignore[no-any-return]
    return NotePipelineService(
        cfg,
        driver_factory=build_note_driver_factory(cfg),
        study_dir_resolver=course_dir_resolver(session_factory, "study_dir"),
        source_dir_resolver=course_dir_resolver(session_factory, "source_dir"),
    )


def register_literature_and_note_tools(mcp: MCPServer, cfg: AppConfig, resolved: dict[str, Any]) -> None:
    """Register literature, Literature Notebook, and note pipeline MCP tools.

    Args:
        mcp: MCPServer instance.
        cfg: Application configuration.
        resolved: Resolved services (`service`, optional `session_factory`, `literature_jobs`,
            `preferences`, `notes`).
    """
    session_factory = resolved.get("session_factory") or sessionmaker(
        bind=create_db_engine(cfg.database_url), expire_on_commit=False
    )
    deps = LiteratureToolDeps(
        service=resolved["service"],
        config=cfg,
        runner=resolved.get("literature_jobs") or _literature_runner(cfg, session_factory),
        session_factory=session_factory,
        preferences=resolved.get("preferences"),
    )
    register_literature_tools(mcp, deps)
    if deps.preferences is not None:
        register_literature_notebook_tools(mcp, deps)
    notes = _note_service(cfg, session_factory, resolved.get("notes"))
    register_note_pipeline_tools(mcp, notes, upload_fn=build_note_upload_fn(cfg))
    gemini_auth = resolved.get("gemini_auth") or build_gemini_auth_service(cfg)
    register_gemini_auth_tools(mcp, gemini_auth, config=cfg)
    register_study_library_tools(mcp, cfg, session_factory)
    register_maintenance_tools(mcp, cfg)
    register_textbook_tools(mcp, cfg, session_factory)
    logger.debug("Registered literature, note pipeline, Gemini auth, and study library MCP tools")

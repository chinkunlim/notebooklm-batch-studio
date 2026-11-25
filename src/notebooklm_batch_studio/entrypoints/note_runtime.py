"""Build the note pipeline and background note scheduler outside a request (web server and MCP; SPEC-020)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.note_driver_factory import build_note_driver_factory
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.services.notes.note_pipeline_service import NotePipelineService
from notebooklm_batch_studio.services.notes.note_scheduler import NoteScheduler

logger = logging.getLogger(__name__)


def _course_dir_resolver(session_factory: Any, attr: str) -> Any:
    """Return a resolver mapping a course code to its `study_dir` or `source_dir`.

    Args:
        session_factory: SQLAlchemy session factory.
        attr: `study_dir` or `source_dir`.

    Returns:
        Callable `(code) -> Path | None`.
    """

    def resolve(code: str) -> Path | None:
        """Look up the folder.

        Args:
            code: Course code.

        Returns:
            Folder path or None.
        """
        with session_factory() as session:
            course = CourseRepository(session).get_course(code)
            value = getattr(course, attr, None) if course else None
        return Path(value) if value else None

    return resolve


def build_note_pipeline(cfg: AppConfig, session_factory: Any) -> NotePipelineService:
    """Create a NotePipelineService that resolves course folders from the database.

    Args:
        cfg: Application configuration.
        session_factory: SQLAlchemy session factory.

    Returns:
        Configured pipeline.
    """
    return NotePipelineService(
        cfg,
        driver_factory=build_note_driver_factory(cfg),
        study_dir_resolver=_course_dir_resolver(session_factory, "study_dir"),
        source_dir_resolver=_course_dir_resolver(session_factory, "source_dir"),
    )


def build_note_scheduler(cfg: AppConfig, session_factory: Any) -> NoteScheduler:
    """Create the persisted Gemini note scheduler.

    Args:
        cfg: Application configuration (`note_schedule_path`).
        session_factory: SQLAlchemy session factory.

    Returns:
        NoteScheduler (its worker thread is started by the web server lifespan).
    """
    return NoteScheduler(cfg.note_schedule_path, lambda: build_note_pipeline(cfg, session_factory))

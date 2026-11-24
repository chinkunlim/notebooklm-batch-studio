"""Shared state and folder lookups for `LiteratureManager` and its mixins (SPEC-012).

Holds the repositories, configuration, and runtime, plus the two lookups every part of the
manager needs: where an item's PDF belongs, and where its PDF actually is on disk.
"""

from __future__ import annotations

import logging
from pathlib import Path

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.literature.tracker import TrackedItem
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol
from notebooklm_batch_studio.domain.study_hierarchy import resolve_literature_dir
from notebooklm_batch_studio.services.literature.protocols import (
    LiteratureRepoProtocol,
    LiteratureRuntimeProtocol,
)
from notebooklm_batch_studio.services.literature.reference_builder import WorkResolver

logger = logging.getLogger(__name__)


class LiteratureManagerBase:
    """Configuration, repositories, runtime, and PDF folder lookups shared by the manager mixins."""

    def __init__(
        self,
        config: AppConfig,
        lit_repo: LiteratureRepoProtocol,
        course_repo: CourseRepositoryProtocol,
        runtime: LiteratureRuntimeProtocol | None = None,
    ) -> None:
        """Initialize the manager with configuration, repositories, and adapter runtime.

        Args:
            config: Application configuration.
            lit_repo: Persistence repository for literature items and jobs.
            course_repo: Persistence repository for courses.
            runtime: Adapter runtime providing HTTP/browser sources and formatters.
        """
        self.config = config
        self.lit_repo = lit_repo
        self.course_repo = course_repo
        self.runtime = runtime
        self._work_resolver: WorkResolver | None = None

    def resolve_target_dir(self, item: TrackedItem) -> Path:
        """Resolve the filesystem folder where an item's PDF should be stored.

        Args:
            item: Tracked literature item.

        Returns:
            Course category/subfolder directory when linked to a course,
            otherwise `config.literature_dir`.
        """
        if item.course_code:
            course = self.course_repo.get_course(item.course_code)
            if course is not None:
                base = Path(course.study_dir) if course.study_dir else Path(course.source_dir)
                target = resolve_literature_dir(base, item.target_category, item.target_subfolder)
                target.mkdir(parents=True, exist_ok=True)
                return target
        unarchived_dir = self.config.scratch_kind_dir("literature")
        unarchived_dir.mkdir(parents=True, exist_ok=True)
        return unarchived_dir

    def resolve_pdf_path(self, key: str) -> Path | None:
        """Return the existing PDF file path for a literature item, if present on disk.

        Only files inside the item's target folder or the unarchived literature folder are
        returned; a stored name that points elsewhere is refused (Refs: ISSUE-047).

        Args:
            key: Literature item key.

        Returns:
            Path to the PDF file, or None.
        """
        item = self.lit_repo.get_item(key)
        if item is None or not item.file:
            return None
        for folder in (self.resolve_target_dir(item), self.config.scratch_kind_dir("literature")):
            root = folder.resolve()
            candidate = (root / item.file).resolve()
            if not candidate.is_relative_to(root):
                logger.warning("Refused literature PDF path outside its folder for %s: %r", key, item.file)
                return None
            if candidate.is_file():
                return candidate
        return None

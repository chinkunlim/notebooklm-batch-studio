"""Archiving side of `LiteratureManager`: file PDFs into courses, unarchive, and auto-register PDFs.

Split from `manager.py` (SPEC-012); behavior is unchanged.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import replace
from pathlib import Path

from notebooklm_batch_studio.domain.literature.tracker import ItemStatus, TrackedItem
from notebooklm_batch_studio.domain.study_hierarchy import (
    DEFAULT_LITERATURE_CATEGORY,
    DEFAULT_LITERATURE_SUBFOLDER,
    resolve_literature_dir,
)
from notebooklm_batch_studio.services.literature.manager_base import LiteratureManagerBase

logger = logging.getLogger(__name__)


def move_review_file(key: str, src_reviews: Path, dst_reviews: Path, review_markdown: str) -> None:
    """Move `<key>_Literature_Review.md` alongside the PDF when archiving/unarchiving.

    Args:
        key: Literature item key.
        src_reviews: Source `reviews/` directory.
        dst_reviews: Destination `reviews/` directory.
        review_markdown: Stored Markdown review text (written if file missing).
    """
    fname = f"{key}_Literature_Review.md"
    src_file, dst_file = src_reviews / fname, dst_reviews / fname
    if src_file.is_file():
        dst_reviews.mkdir(parents=True, exist_ok=True)
        if src_file.resolve() != dst_file.resolve():
            shutil.move(str(src_file), str(dst_file))
    elif review_markdown:
        dst_reviews.mkdir(parents=True, exist_ok=True)
        dst_file.write_text(review_markdown, encoding="utf-8")


def _move_pdf_with_review(item: TrackedItem, src_pdf: Path, dest_dir: Path) -> Path:
    """Move a PDF (and its Literature Review file) into `dest_dir` unless it is already there.

    Args:
        item: Literature item the PDF belongs to.
        src_pdf: Current PDF location.
        dest_dir: Destination folder.

    Returns:
        The PDF's new path.
    """
    dest_pdf = dest_dir / src_pdf.name
    if src_pdf.resolve() != dest_pdf.resolve():
        dest_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_pdf), str(dest_pdf))
        move_review_file(item.key, src_pdf.parent / "reviews", dest_dir / "reviews", item.review_markdown)
    return dest_pdf


def _unique_key(stem: str, taken_keys: set[str]) -> str:
    """Pick a key based on a file stem that is not yet used, and reserve it.

    Args:
        stem: PDF file stem.
        taken_keys: Already-used keys (mutated in place).

    Returns:
        The reserved key (`stem`, `stem_2`, `stem_3`, ...).
    """
    key, suffix = stem, 2
    while key in taken_keys:
        key, suffix = f"{stem}_{suffix}", suffix + 1
    taken_keys.add(key)
    return key


class LiteratureArchiveMixin(LiteratureManagerBase):
    """Moves literature PDFs between the staging folder and course folders."""

    def _require_importable(self, key: str, course_code: str | None) -> tuple[TrackedItem, str, Path]:
        """Check that an item, its target course, and its PDF all exist.

        Args:
            key: Literature item key.
            course_code: Optional course code override.

        Returns:
            Tuple of `(item, target_course_code, current_pdf_path)`.

        Raises:
            ValueError: When item or target course is missing, or PDF is not downloaded yet.
        """
        item = self.lit_repo.get_item(key)
        if item is None:
            raise ValueError(f"Literature item not found: {key}")
        target_code = course_code or item.course_code
        if not target_code or self.course_repo.get_course(target_code) is None:
            raise ValueError("Please link a valid course before importing.")
        src_pdf = self.resolve_pdf_path(key)
        if src_pdf is None or not src_pdf.is_file():
            raise ValueError("PDF has not been downloaded yet.")
        return item, target_code, src_pdf

    def import_to_course(
        self,
        key: str,
        course_code: str | None = None,
        category: str | None = None,
        subfolder: str | None = None,
    ) -> TrackedItem:
        """Ensure a downloaded PDF is stored in the linked course directory and marked imported.

        Args:
            key: Literature item key.
            course_code: Optional course code override if item was not yet linked.
            category: Optional target study category override.
            subfolder: Optional target subfolder override.

        Returns:
            Updated `TrackedItem`.

        Raises:
            ValueError: When item or target course is missing, or PDF is not downloaded yet.
        """
        item, target_code, src_pdf = self._require_importable(key, course_code)
        updated_item = replace(
            item,
            course_code=target_code,
            target_category=category or item.target_category,
            target_subfolder=subfolder if subfolder is not None else item.target_subfolder,
        )
        dest_pdf = _move_pdf_with_review(item, src_pdf, self.resolve_target_dir(updated_item))
        saved = replace(updated_item, file=dest_pdf.name, imported_to_course=True)
        self.lit_repo.upsert_item(saved)
        logger.info("Archived literature %s into course %s (%s)", key, target_code, dest_pdf)
        return saved

    def unarchive_item(self, key: str) -> TrackedItem:
        """Move an archived literature PDF back to the unarchived staging folder.

        Args:
            key: Literature item key.

        Returns:
            Updated unarchived `TrackedItem`.

        Raises:
            ValueError: When item is not found.
        """
        item = self.lit_repo.get_item(key)
        if item is None:
            raise ValueError(f"Literature item not found: {key}")
        src_pdf = self.resolve_pdf_path(key)
        self.config.literature_dir.mkdir(parents=True, exist_ok=True)
        if src_pdf is not None and src_pdf.is_file():
            _move_pdf_with_review(item, src_pdf, self.config.literature_dir)
        saved = replace(item, course_code=None, imported_to_course=False)
        self.lit_repo.upsert_item(saved)
        logger.info("Moved literature %s back to unarchived folder", key)
        return saved

    def _discovered_item(self, pdf: Path, key: str, course_code: str | None) -> TrackedItem:
        """Build the tracker entry for a PDF found on disk but not yet tracked.

        Args:
            pdf: Discovered PDF file.
            key: Reserved item key.
            course_code: Course code when found in a course's `Literature_Review` folder.

        Returns:
            New `TrackedItem` marked as downloaded.
        """
        hint = self.runtime.extract_pdf_hint(pdf) if self.runtime else pdf.stem.replace("_", " ")
        return TrackedItem(
            key=key,
            input=hint,
            reference=None,
            apa=pdf.stem,
            status=ItemStatus.DOWNLOADED,
            file=pdf.name,
            note="auto-discovered from folder (pending source lookup)",
            course_code=course_code,
            target_category=DEFAULT_LITERATURE_CATEGORY,
            target_subfolder=DEFAULT_LITERATURE_SUBFOLDER,
            imported_to_course=bool(course_code),
        )

    def _register_dir_pdfs(
        self,
        folder: Path,
        known_files: set[str],
        taken_keys: set[str],
        course_code: str | None = None,
    ) -> list[str]:
        """Register any untracked `*.pdf` files found in `folder` into `lit_repo`.

        Args:
            folder: Directory to scan.
            known_files: Set of already-tracked PDF filenames (mutated in place).
            taken_keys: Set of already-used item keys (mutated in place).
            course_code: Optional course code if scanning a course's `Literature_Review`.

        Returns:
            List of newly registered item keys.
        """
        if not folder.is_dir():
            return []
        added_keys: list[str] = []
        for pdf in sorted(folder.glob("*.pdf")):
            if pdf.name.startswith(".") or pdf.name in known_files:
                continue
            key = _unique_key(pdf.stem, taken_keys)
            known_files.add(pdf.name)
            self.lit_repo.upsert_item(self._discovered_item(pdf, key, course_code))
            added_keys.append(key)
        return added_keys

    def sync_untracked_pdfs(self) -> list[str]:
        """Auto-register untracked PDFs in `scratch/literature` and course `Literature_Review` dirs.

        Returns:
            List of newly registered item keys.
        """
        self.config.literature_dir.mkdir(parents=True, exist_ok=True)
        items = self.lit_repo.list_items()
        known_files = {item.file for item in items if item.file}
        taken_keys = {item.key for item in items}
        added_keys = self._register_dir_pdfs(self.config.literature_dir, known_files, taken_keys)
        for course in self.course_repo.list_courses():
            base = Path(course.study_dir) if course.study_dir else Path(course.source_dir)
            lit_dir = resolve_literature_dir(base, DEFAULT_LITERATURE_CATEGORY, DEFAULT_LITERATURE_SUBFOLDER)
            added_keys.extend(
                self._register_dir_pdfs(lit_dir, known_files, taken_keys, course_code=course.code)
            )
        if added_keys:
            logger.info("Auto-registered %d untracked literature PDFs", len(added_keys))
        return added_keys

"""pypdf adapter for textbook splitting: read bookmarks, write a page range with its bookmarks (SPEC-018)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import pypdf

from notebooklm_batch_studio.domain.textbook_sections import OutlineEntry, PageRangeJob

logger = logging.getLogger(__name__)


class PypdfTextbookTools:
    """Read outlines and extract page ranges with pypdf (BSD licence; no PyMuPDF/AGPL)."""

    def read_outline(self, pdf: Path) -> tuple[list[OutlineEntry], int]:
        """Read a PDF's bookmarks as a flat list in document order.

        Args:
            pdf: Source PDF path.

        Returns:
            `(entries, total_pages)`; bookmarks whose destination cannot be resolved are skipped.
        """
        reader = pypdf.PdfReader(str(pdf))
        entries: list[OutlineEntry] = []
        self._flatten(reader, reader.outline, 1, entries)
        return entries, len(reader.pages)

    def _flatten(
        self, reader: pypdf.PdfReader, items: list[Any], level: int, out: list[OutlineEntry]
    ) -> None:
        """Append nested outline items to `out`, tracking depth.

        Args:
            reader: Open PDF reader.
            items: pypdf outline list (nested lists are children).
            level: Current depth (1 = top).
            out: Accumulator list.
        """
        for item in items:
            if isinstance(item, list):
                self._flatten(reader, item, level + 1, out)
                continue
            try:
                index = reader.get_destination_page_number(item)
            except Exception as exc:  # malformed destinations are common in scanned books
                logger.debug("Skip bookmark %r: %s", getattr(item, "title", ""), exc)
                continue
            if index is not None:
                out.append(OutlineEntry(level, str(item.title or "").strip(), index + 1))

    def write_pages(self, job: PageRangeJob) -> None:
        """Write pages `job.start..job.end` (1-based, inclusive) of `job.source` to `job.dest`.

        Args:
            job: Source, page range, destination and chapter-relative bookmarks.
        """
        reader = pypdf.PdfReader(str(job.source))
        writer = pypdf.PdfWriter()
        for index in range(job.start - 1, job.end):
            writer.add_page(reader.pages[index])
        parents: dict[int, Any] = {}
        for mark in job.bookmarks:
            parents[mark.level] = writer.add_outline_item(
                mark.title, mark.page - 1, parent=parents.get(mark.level - 1)
            )
        tmp = job.dest.with_name(f".{job.dest.name}.part")
        with tmp.open("wb") as fh:
            writer.write(fh)
        os.replace(tmp, job.dest)
        logger.info("Wrote %s (pages %d-%d)", job.dest.name, job.start, job.end)

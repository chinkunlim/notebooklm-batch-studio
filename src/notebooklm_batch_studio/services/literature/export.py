"""Reporting side of `LiteratureManager`: Markdown report, APA 7 list, and API serialization.

Split from `manager.py` (SPEC-012); behavior is unchanged.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime
from typing import Any

from notebooklm_batch_studio.domain.literature.tracker import TrackedItem
from notebooklm_batch_studio.services.literature.manager_base import LiteratureManagerBase

logger = logging.getLogger(__name__)


def apa_to_html(apa: str) -> str:
    """Render APA 7 Markdown italics (`*...*`) as escaped HTML `<i>...</i>`.

    Args:
        apa: APA 7 string with optional Markdown italics.

    Returns:
        HTML-safe string with `<i>` tags.
    """
    return re.sub(r"\*([^*]+)\*", r"<i>\1</i>", html.escape(apa))


class LiteratureExportMixin(LiteratureManagerBase):
    """Exports and serializes tracked literature."""

    def export_report(self, course_code: str | None = None) -> str:
        """Render the Markdown download report for all or course-filtered items.

        Args:
            course_code: Optional course filter.

        Returns:
            Markdown report content.
        """
        items = self.lit_repo.list_items(course_code=course_code)
        stamp = f"{datetime.now():%Y-%m-%d %H:%M}"
        if self.runtime is not None:
            return self.runtime.render_report(items, "Literature_Review", stamp)
        return "\n".join(f"- [{i.status.value}] {i.apa}" for i in items)

    def export_apa_list(
        self, course_code: str | None = None, keys: list[str] | None = None
    ) -> dict[str, Any]:
        """Return sorted APA 7 citations in plain text and HTML (preserving italics).

        Args:
            course_code: Optional course filter.
            keys: Optional list of item keys to include; None includes all items.

        Returns:
            Dictionary with `count`, `plain`, and `html` keys.
        """
        raw = self.lit_repo.list_items(course_code=course_code)
        if keys:
            wanted = set(keys)
            raw = [item for item in raw if item.key in wanted]
        items = sorted(raw, key=self.runtime.sort_key) if self.runtime else sorted(raw, key=lambda x: x.apa)
        apas = [item.apa for item in items if item.apa]
        return {
            "count": len(apas),
            "plain": "\n\n".join(apas),
            "html": "".join(f"<p>{apa_to_html(apa)}</p>" for apa in apas),
        }

    def serialize_item(self, item: TrackedItem, stage: str = "") -> dict[str, Any]:
        """Serialize a `TrackedItem` for HTTP API and MCP responses.

        Args:
            item: Tracked literature item.
            stage: Live stage label when a job is currently processing this item.

        Returns:
            JSON-serializable dictionary.
        """
        if self.runtime is not None:
            status_label, src_label, notes = self.runtime.format_notes_and_source(item)
        else:
            status_label, src_label, notes = item.status.value, item.source, item.note
        return {
            "key": item.key,
            "input": item.input,
            "apa": item.apa,
            "apa_html": apa_to_html(item.apa),
            "status": item.status.value,
            "status_label": status_label,
            "kind": item.reference.kind.value if item.reference else "",
            "doi": item.reference.doi if item.reference else "",
            "file": item.file,
            "file_url": f"/api/literature/{item.key}/pdf" if item.file else "",
            "source": src_label,
            "notes": notes,
            "stage": stage,
            "course_code": item.course_code,
            "target_category": item.target_category,
            "target_subfolder": item.target_subfolder,
            "imported_to_course": item.imported_to_course,
            "source_id": item.source_id,
            "has_review": bool(item.review_markdown),
            "review_markdown": item.review_markdown,
        }

"""One-time / idempotent importer from standalone `literature-fetch` SQLite DB & PDFs."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.domain.literature.literature import Reference, ReferenceKind
from notebooklm_batch_studio.domain.literature.tracker import ItemStatus, TrackedItem

logger = logging.getLogger(__name__)


def _row_to_tracked_item(row: sqlite3.Row) -> TrackedItem:
    """Convert one `items` row from legacy `literature.db` into a `TrackedItem`.

    Args:
        row: SQLite row from legacy `items` table.

    Returns:
        Constructed `TrackedItem`.
    """
    ref: Reference | None = None
    if row["has_reference"]:
        raw_kind = str(row["kind"] or "article")
        kind = (
            ReferenceKind(raw_kind) if raw_kind in ReferenceKind._value2member_map_ else ReferenceKind.ARTICLE
        )
        urls = tuple(u for u in str(row["pdf_urls"] or "").splitlines() if u.strip())
        ref = Reference(
            key=str(row["key"]),
            citation=str(row["citation"] or row["apa"] or row["input"]),
            doi=str(row["doi"] or ""),
            kind=kind,
            arxiv_id=str(row["arxiv_id"] or ""),
            pdf_urls=urls,
            title=str(row["title"] or ""),
            author=str(row["author"] or ""),
        )
    raw_status = str(row["status"] or "pending")
    status = ItemStatus(raw_status) if raw_status in ItemStatus._value2member_map_ else ItemStatus.PENDING
    return TrackedItem(
        key=str(row["key"]),
        input=str(row["input"]),
        reference=ref,
        apa=str(row["apa"] or row["input"]),
        status=status,
        file=str(row["file"] or ""),
        note=str(row["note"] or ""),
        source=str(row["source"] or ""),
        check=str(row["check_note"] or ""),
        course_code=None,
        imported_to_course=False,
    )


def import_legacy_literature_db(
    legacy_db: Path,
    legacy_pdf_dir: Path,
    lit_repo: LiteratureRepository,
    target_pdf_dir: Path,
) -> dict[str, Any]:
    """Import items and PDFs from standalone `literature-fetch` into `LiteratureRepository`.

    Existing keys in `lit_repo` are preserved without overwriting.

    Args:
        legacy_db: Path to `literature-fetch/db/literature.db`.
        legacy_pdf_dir: Path to `literature-fetch/output/literature/`.
        lit_repo: Destination `LiteratureRepository`.
        target_pdf_dir: Destination staging directory (`config.literature_dir`).

    Returns:
        Summary dictionary with `imported`, `skipped`, and `copied_pdfs` counts.
    """
    if not legacy_db.is_file():
        return {"imported": 0, "skipped": 0, "copied_pdfs": 0}

    target_pdf_dir.mkdir(parents=True, exist_ok=True)
    existing_keys = {item.key for item in lit_repo.list_items()}
    imported = 0
    skipped = 0
    copied_pdfs = 0

    conn = sqlite3.connect(f"file:{legacy_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM items ORDER BY position, key").fetchall()
        for row in rows:
            item = _row_to_tracked_item(row)
            if item.key in existing_keys:
                skipped += 1
                continue
            if item.file and legacy_pdf_dir.is_dir():
                src_pdf = legacy_pdf_dir / item.file
                dst_pdf = target_pdf_dir / item.file
                if src_pdf.is_file() and not dst_pdf.exists():
                    shutil.copy2(src_pdf, dst_pdf)
                    copied_pdfs += 1
            lit_repo.upsert_item(item, position=int(row["position"]))
            imported += 1
    finally:
        conn.close()

    logger.info(
        "Imported legacy literature: imported=%d skipped=%d copied_pdfs=%d",
        imported,
        skipped,
        copied_pdfs,
    )
    return {"imported": imported, "skipped": skipped, "copied_pdfs": copied_pdfs}

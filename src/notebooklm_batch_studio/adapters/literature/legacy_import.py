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


def _reference_from_row(row: sqlite3.Row) -> Reference | None:
    """Rebuild the identified `Reference` stored in a legacy `items` row.

    Args:
        row: SQLite row from legacy `items` table.

    Returns:
        The reference, or None when the legacy item was never identified.
    """
    if not row["has_reference"]:
        return None
    raw_kind = str(row["kind"] or "article")
    kind = ReferenceKind(raw_kind) if raw_kind in ReferenceKind._value2member_map_ else ReferenceKind.ARTICLE
    return Reference(
        key=str(row["key"]),
        citation=str(row["citation"] or row["apa"] or row["input"]),
        doi=str(row["doi"] or ""),
        kind=kind,
        arxiv_id=str(row["arxiv_id"] or ""),
        pdf_urls=tuple(u for u in str(row["pdf_urls"] or "").splitlines() if u.strip()),
        title=str(row["title"] or ""),
        author=str(row["author"] or ""),
    )


def safe_pdf_name(raw: str) -> str:
    """Accept a legacy PDF file name only when it is a bare `.pdf` name (Refs: ISSUE-047).

    Args:
        raw: File name stored in the legacy database.

    Returns:
        The same name, or "" when it contains a folder part, is hidden, or is not a PDF.
    """
    if not raw or Path(raw).name != raw or raw.startswith(".") or not raw.lower().endswith(".pdf"):
        if raw:
            logger.warning("Ignored unsafe legacy literature file name: %r", raw)
        return ""
    return raw


def _row_to_tracked_item(row: sqlite3.Row) -> TrackedItem:
    """Convert one `items` row from legacy `literature.db` into a `TrackedItem`.

    Args:
        row: SQLite row from legacy `items` table.

    Returns:
        Constructed `TrackedItem`.
    """
    raw_status = str(row["status"] or "pending")
    status = ItemStatus(raw_status) if raw_status in ItemStatus._value2member_map_ else ItemStatus.PENDING
    return TrackedItem(
        key=str(row["key"]),
        input=str(row["input"]),
        reference=_reference_from_row(row),
        apa=str(row["apa"] or row["input"]),
        status=status,
        file=safe_pdf_name(str(row["file"] or "")),
        note=str(row["note"] or ""),
        source=str(row["source"] or ""),
        check=str(row["check_note"] or ""),
        course_code=None,
        imported_to_course=False,
    )


def _copy_pdf(file_name: str, legacy_pdf_dir: Path, target_pdf_dir: Path) -> bool:
    """Copy one legacy PDF into the staging folder without overwriting.

    Args:
        file_name: Bare PDF file name (already validated).
        legacy_pdf_dir: Legacy `output/literature/` folder.
        target_pdf_dir: Destination staging folder.

    Returns:
        True when a file was copied.
    """
    if not file_name or not legacy_pdf_dir.is_dir():
        return False
    src_pdf, dst_pdf = legacy_pdf_dir / file_name, target_pdf_dir / file_name
    if not src_pdf.is_file() or dst_pdf.exists():
        return False
    shutil.copy2(src_pdf, dst_pdf)
    return True


def _read_legacy_rows(legacy_db: Path) -> list[sqlite3.Row]:
    """Read all legacy `items` rows in their original order (read-only connection).

    Args:
        legacy_db: Path to the legacy SQLite database.

    Returns:
        Rows ordered by position and key.
    """
    conn = sqlite3.connect(f"file:{legacy_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM items ORDER BY position, key").fetchall()
    finally:
        conn.close()


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
    summary = {"imported": 0, "skipped": 0, "copied_pdfs": 0}
    if not legacy_db.is_file():
        return summary
    target_pdf_dir.mkdir(parents=True, exist_ok=True)
    existing_keys = {item.key for item in lit_repo.list_items()}
    for row in _read_legacy_rows(legacy_db):
        item = _row_to_tracked_item(row)
        if item.key in existing_keys:
            summary["skipped"] += 1
            continue
        summary["copied_pdfs"] += int(_copy_pdf(item.file, legacy_pdf_dir, target_pdf_dir))
        lit_repo.upsert_item(item, position=int(row["position"]))
        summary["imported"] += 1
    logger.info("Imported legacy literature: %s", summary)
    return summary

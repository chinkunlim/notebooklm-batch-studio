"""SQLite/SQLAlchemy repository for tracked literature items and fetch jobs (SPEC-012)."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from notebooklm_batch_studio.adapters.db.models import LiteratureItemRecord, LiteratureJobRecord
from notebooklm_batch_studio.domain.literature.literature import Reference, ReferenceKind
from notebooklm_batch_studio.domain.literature.tracker import ItemStatus, Job, JobState, TrackedItem
from notebooklm_batch_studio.domain.study_hierarchy import DEFAULT_LITERATURE_CATEGORY

logger = logging.getLogger(__name__)


def _to_reference(row: LiteratureItemRecord) -> Reference | None:
    """Reconstruct a `Reference` from a `LiteratureItemRecord` row if identified.

    Args:
        row: Database row from `literature_items`.

    Returns:
        `Reference` instance or None when unresolved.
    """
    if not (row.title or row.doi or row.authors):
        return None
    kind = ReferenceKind(row.kind) if row.kind in ReferenceKind._value2member_map_ else ReferenceKind.ARTICLE
    pdf_urls = tuple(json.loads(row.publisher)) if (row.publisher or "").startswith("[") else ()
    return Reference(
        key=row.key,
        citation=row.apa or row.input_text,
        doi=row.doi or "",
        kind=kind,
        arxiv_id=row.volume or "",
        pdf_urls=pdf_urls,
        title=row.title or "",
        author=row.authors or "",
    )


def _to_domain_item(row: LiteratureItemRecord) -> TrackedItem:
    """Convert a `LiteratureItemRecord` ORM row into an immutable `TrackedItem`.

    Args:
        row: Database row from `literature_items`.

    Returns:
        Domain `TrackedItem` instance.
    """
    status = ItemStatus(row.status) if row.status in ItemStatus._value2member_map_ else ItemStatus.PENDING
    return TrackedItem(
        key=row.key,
        input=row.input_text,
        reference=_to_reference(row),
        apa=row.apa or row.input_text,
        status=status,
        file=row.file or "",
        note=row.note or "",
        source=row.source or "",
        check=row.check_note or "",
        course_code=row.course_code,
        target_category=row.target_category or DEFAULT_LITERATURE_CATEGORY,
        target_subfolder=row.target_subfolder or "Literature_Review",
        imported_to_course=bool(row.imported_to_course),
        source_id=row.source_id,
        review_markdown=getattr(row, "review_markdown", "") or "",
    )


def _to_domain_job(row: LiteratureJobRecord) -> Job:
    """Convert a `LiteratureJobRecord` ORM row into a `Job`.

    Args:
        row: Database row from `literature_jobs`.

    Returns:
        Domain `Job` instance.
    """
    state = JobState(row.state) if row.state in JobState._value2member_map_ else JobState.FAILED
    return Job(
        id=row.id,
        kind=row.kind,
        state=state,
        total=row.total,
        done=row.done,
        message=row.message,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


class LiteratureRepository:
    """Persistence operations for literature items and background fetch jobs."""

    def __init__(self, session: Session) -> None:
        """Bind repository to an active SQLAlchemy session.

        Args:
            session: Open SQLAlchemy session.
        """
        self.session = session

    def list_items(self, course_code: str | None = None) -> list[TrackedItem]:
        """Return tracked literature items ordered by position.

        Args:
            course_code: Optional course filter; None returns all items.

        Returns:
            List of `TrackedItem` entities.
        """
        stmt = select(LiteratureItemRecord).order_by(LiteratureItemRecord.position, LiteratureItemRecord.key)
        if course_code:
            stmt = stmt.where(LiteratureItemRecord.course_code == course_code)
        rows = self.session.scalars(stmt).all()
        return [_to_domain_item(row) for row in rows]

    def get_item(self, key: str) -> TrackedItem | None:
        """Fetch a single literature item by key.

        Args:
            key: Unique literature item key.

        Returns:
            `TrackedItem` if found, else None.
        """
        row = self.session.get(LiteratureItemRecord, key)
        return _to_domain_item(row) if row is not None else None

    def upsert_item(self, item: TrackedItem, position: int | None = None) -> None:
        """Insert or update a `TrackedItem` in `literature_items`.

        Args:
            item: Domain item to persist.
            position: Optional explicit ordering position.
        """
        row = self.session.get(LiteratureItemRecord, item.key)
        if row is None:
            pos = position if position is not None else self._next_position()
            row = LiteratureItemRecord(key=item.key, position=pos, input_text=item.input)
            self.session.add(row)
        self._apply_item_fields(row, item)
        self.session.flush()
        self.session.commit()

    def replace_key(self, old_key: str, item: TrackedItem) -> None:
        """Replace an item's primary key (e.g. `Unresolved_1` -> `Smith_2024_Title`).

        Args:
            old_key: Previous primary key to remove.
            item: Updated item carrying the new key.
        """
        old_row = self.session.get(LiteratureItemRecord, old_key)
        pos = old_row.position if old_row is not None else self._next_position()
        if old_row is not None and old_key != item.key:
            self.session.delete(old_row)
            self.session.flush()
        self.upsert_item(item, position=pos)

    def delete_item(self, key: str) -> bool:
        """Delete a literature item by key.

        Args:
            key: Primary key of the item to delete.

        Returns:
            True if a row was deleted, False if not found.
        """
        result = self.session.execute(delete(LiteratureItemRecord).where(LiteratureItemRecord.key == key))
        self.session.commit()
        return int(result.rowcount or 0) > 0  # type: ignore[attr-defined]

    def mark_imported(self, key: str, source_id: str | None = None) -> TrackedItem | None:
        """Mark a literature item as imported into its linked course.

        Args:
            key: Literature item key.
            source_id: Optional Gemini Notebook source ID.

        Returns:
            Updated `TrackedItem`, or None if not found.
        """
        row = self.session.get(LiteratureItemRecord, key)
        if row is None:
            return None
        row.imported_to_course = True
        if source_id is not None:
            row.source_id = source_id
        self.session.commit()
        return _to_domain_item(row)

    def start_job(self, kind: str, total: int, message: str = "") -> Job:
        """Create and persist a running literature fetch job.

        Args:
            kind: Job type (`download`, `identify`, `interactive`).
            total: Number of items queued.
            message: Initial status message.

        Returns:
            Created `Job` entity.
        """
        now = datetime.now(timezone.utc).isoformat()
        row = LiteratureJobRecord(
            kind=kind,
            state=JobState.RUNNING.value,
            total=total,
            done=0,
            message=message,
            started_at=now,
        )
        self.session.add(row)
        self.session.commit()
        return _to_domain_job(row)

    def update_job(self, job_id: int, done: int, message: str) -> None:
        """Update progress counters and message on a running job.

        Args:
            job_id: Job primary key.
            done: Completed items count.
            message: Latest status text.
        """
        row = self.session.get(LiteratureJobRecord, job_id)
        if row is None:
            return
        row.done = done
        row.message = message
        self.session.commit()

    def finish_job(self, job_id: int, state: JobState, message: str = "") -> Job | None:
        """Mark a literature job as done or failed.

        Args:
            job_id: Job primary key.
            state: Final `JobState` (`DONE` or `FAILED`).
            message: Optional completion summary or error text.

        Returns:
            Updated `Job` or None if missing.
        """
        row = self.session.get(LiteratureJobRecord, job_id)
        if row is None:
            return None
        row.state = state.value
        if message:
            row.message = message
        row.finished_at = datetime.now(timezone.utc).isoformat()
        self.session.commit()
        return _to_domain_job(row)

    def latest_job(self) -> Job | None:
        """Return the most recent literature fetch job, if any.

        Returns:
            Latest `Job` or None.
        """
        stmt = select(LiteratureJobRecord).order_by(LiteratureJobRecord.id.desc()).limit(1)
        row = self.session.scalars(stmt).first()
        return _to_domain_job(row) if row is not None else None

    def close_stale_jobs(self, message: str = "前次程序已中斷，工作未完成") -> int:
        """Mark leftover `running` literature jobs as failed (Refs: ISSUE-054).

        Called on runner startup when no background worker thread is active.

        Args:
            message: Explanation recorded on closed jobs.

        Returns:
            Number of stale jobs marked failed.
        """
        now = datetime.now(timezone.utc).isoformat()
        result = self.session.execute(
            update(LiteratureJobRecord)
            .where(LiteratureJobRecord.state == JobState.RUNNING.value)
            .values(state=JobState.FAILED.value, message=message, finished_at=now)
        )
        self.session.commit()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def _next_position(self) -> int:
        """Compute the next sequential display position.

        Returns:
            Integer position value.
        """
        max_pos = self.session.scalar(select(func.max(LiteratureItemRecord.position)))
        return (int(max_pos) + 1) if max_pos is not None else 0

    def _apply_item_fields(self, row: LiteratureItemRecord, item: TrackedItem) -> None:
        """Copy domain `TrackedItem` fields onto an ORM `LiteratureItemRecord`.

        Args:
            row: Target ORM record.
            item: Source domain entity.
        """
        row.input_text = item.input
        row.apa = item.apa
        row.status = item.status.value
        row.file = item.file
        row.note = item.note
        row.source = item.source
        row.check_note = item.check
        row.course_code = item.course_code
        row.target_category = item.target_category
        row.target_subfolder = item.target_subfolder
        row.imported_to_course = item.imported_to_course
        row.source_id = item.source_id
        row.review_markdown = item.review_markdown
        ref = item.reference
        if ref is not None:
            row.kind = ref.kind.value
            row.doi = ref.doi
            row.authors = ref.author
            row.title = ref.title
            row.volume = ref.arxiv_id
            row.publisher = json.dumps(list(ref.pdf_urls))
        else:
            row.kind = ReferenceKind.ARTICLE.value
            row.doi = ""
            row.authors = ""
            row.title = ""
            row.volume = ""
            row.publisher = "[]"


def with_status(item: TrackedItem, status: ItemStatus, **changes: object) -> TrackedItem:
    """Return a copy of `TrackedItem` with updated status and optional fields.

    Args:
        item: Original tracked item.
        status: New `ItemStatus`.
        **changes: Additional dataclass fields to update.

    Returns:
        Updated `TrackedItem`.
    """
    return replace(item, status=status, **changes)  # type: ignore[arg-type]

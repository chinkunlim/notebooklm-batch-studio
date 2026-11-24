"""Domain model of the reference tracker: one item per line of the user's Markdown list (ADR-005)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from notebooklm_batch_studio.domain.literature.literature import Reference
from notebooklm_batch_studio.domain.study_hierarchy import DEFAULT_LITERATURE_CATEGORY


class ItemStatus(str, Enum):
    """Where an item of the list stands."""

    PENDING = "pending"
    DOWNLOADED = "downloaded"
    DOWNLOADED_COPY = "downloaded_copy"
    NEEDS_REVIEW = "needs_review"
    BORROW = "borrow"
    UNAVAILABLE = "unavailable"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class TrackedItem:
    """One entry of the user's reference list.

    Attributes:
        key: Unique key (file name stem); `Unresolved_N` for inputs not identified yet.
        input: The line as the user wrote it.
        reference: What to download; None when the work could not be identified.
        apa: APA 7 reference (the input text when not identified).
        status: Current status.
        file: Saved PDF file name; empty when none.
        note: Latest download note (blocked sites, author copy, latest book edition, ...).
        source: URL the PDF came from.
        check: Note from identifying the work (e.g. matched by title search) that stays visible.
        course_code: Optional linked course code (`courses.code`).
        target_category: Target study folder category (default `01 Materials`).
        target_subfolder: Target subfolder inside the category (default `Literature_Review`).
        imported_to_course: Whether the PDF has been registered/imported into the linked course.
        source_id: Gemini Notebook source ID if uploaded.
        review_markdown: Generated Western-university-style Literature Review in Markdown.
    """

    key: str
    input: str
    reference: Reference | None
    apa: str
    status: ItemStatus
    file: str = ""
    note: str = ""
    source: str = ""
    check: str = ""
    course_code: str | None = None
    target_category: str = DEFAULT_LITERATURE_CATEGORY
    target_subfolder: str = "Literature_Review"
    imported_to_course: bool = False
    source_id: str | None = None
    review_markdown: str = ""


class JobState(str, Enum):
    """State of a background processing job."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class Job:
    """One processing run (from the command line, the web page or an API call).

    Attributes:
        id: Job number.
        kind: What the job does (e.g. `download`, `identify`).
        state: Running, done or failed.
        total: Number of items to process.
        done: Items finished so far.
        message: Latest progress text (e.g. the key being processed).
        started_at: Start time (ISO 8601, UTC).
        finished_at: End time; None while running.
    """

    id: int
    kind: str
    state: JobState
    total: int
    done: int
    message: str
    started_at: str
    finished_at: str | None


class AlreadyRunningError(Exception):
    """Another processing job is running (only one may use the browser and the list at a time)."""

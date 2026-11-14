"""Domain entities for Gemini Notebook Q&A notes, tags, and mastery lifecycle (SPEC-011)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol


class MasteryStatus(str, Enum):
    """Learning mastery state for a Q&A note."""

    NEEDS_REVIEW = "needs_review"
    MASTERED = "mastered"


class NoteScene(str, Enum):
    """Originating context where the question was asked."""

    CHAT_DRAWER = "chat_drawer"
    STUDY_TAB = "study_tab"
    QUIZ_EXPLAIN = "quiz_explain"


@dataclass
class CourseQANote:
    """A persistent Markdown study note extracted from Gemini Notebook Q&A discussions.

    Attributes:
        id: Unique note identifier (e.g., `note-20261114-1701`).
        course_code: Course identifier code.
        lecture_no: Sequence number of lecture, or None if course-wide.
        title: Note title summarizing the core question or concept.
        content_markdown: Body text formatted in Markdown.
        personal_memo: Optional personal annotation or student reminder.
        tags: List of hierarchical tags (e.g., `課程/BIO101/L03`, `掌握度/待加強`).
        source_scene: Originating scene identifier.
        mastery_status: Current mastery status (`needs_review` or `mastered`).
        is_uploaded_as_source: Whether this note has been pushed to Gemini Notebook.
        uploaded_source_id: Remote source identifier if uploaded.
        created_at: Creation timestamp (UTC).
        updated_at: Last modification timestamp (UTC).
    """

    id: str
    course_code: str
    title: str
    content_markdown: str
    lecture_no: int | None = None
    personal_memo: str | None = None
    tags: list[str] = field(default_factory=list)
    source_scene: str = NoteScene.CHAT_DRAWER.value
    mastery_status: str = MasteryStatus.NEEDS_REVIEW.value
    is_uploaded_as_source: bool = False
    uploaded_source_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QANoteRepositoryProtocol(Protocol):
    """Persistence contract for Q&A notes."""

    def upsert_note(self, note: CourseQANote) -> CourseQANote:
        """Insert or update a CourseQANote record.

        Args:
            note: CourseQANote entity to save.

        Returns:
            Saved CourseQANote.
        """
        ...

    def get_note(self, note_id: str) -> CourseQANote | None:
        """Fetch one note by ID.

        Args:
            note_id: Note primary key.

        Returns:
            CourseQANote or None if missing.
        """
        ...

    def list_notes(
        self,
        course_code: str | None = None,
        lecture_no: int | None = None,
        mastery_status: str | None = None,
    ) -> list[CourseQANote]:
        """List notes with optional filters.

        Args:
            course_code: Course identifier filter.
            lecture_no: Lecture sequence filter.
            mastery_status: Mastery filter.

        Returns:
            List of matching CourseQANote objects.
        """
        ...

    def delete_note(self, note_id: str) -> bool:
        """Delete one note by ID.

        Args:
            note_id: Note primary key.

        Returns:
            True if deleted, False otherwise.
        """
        ...


class NotebookLMRemoteAdminProtocol(Protocol):
    """Protocol extension for remote artifact administration."""

    async def delete_artifact(self, notebook_id: str, artifact_id: str) -> None:
        """Delete a remote artifact from a notebook.

        Args:
            notebook_id: Notebook identifier.
            artifact_id: Remote artifact identifier.
        """
        ...

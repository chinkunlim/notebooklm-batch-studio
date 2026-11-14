"""Domain entities for Gemini Notebook Q&A notes, tags, and mastery lifecycle (SPEC-011)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol


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

    async def generate_cinematic_video(
        self,
        notebook_id: str,
        instructions: str,
        source_ids: list[str] | None = None,
        language: str = "zh-TW",
    ) -> str:
        """Generate a cinematic video overview in a notebook.

        Args:
            notebook_id: Notebook identifier.
            instructions: Prompt or focus instructions.
            source_ids: Optional source IDs to scope generation.
            language: Output language code.

        Returns:
            Generated remote artifact identifier.
        """
        ...

    async def revise_slide(self, notebook_id: str, artifact_id: str, slide_index: int, prompt: str) -> str:
        """Revise a single slide in an existing slide deck artifact.

        Args:
            notebook_id: Notebook identifier.
            artifact_id: Existing slide deck artifact identifier.
            slide_index: Zero-based slide index to revise.
            prompt: Revision instructions.

        Returns:
            Revised artifact identifier.
        """
        ...

    async def export_artifact(
        self, notebook_id: str, artifact_id: str, title: str = "Export", kind: str = "report"
    ) -> dict[str, Any]:
        """Export a remote report or data table to Google Docs or Sheets.

        Args:
            notebook_id: Notebook identifier.
            artifact_id: Remote artifact identifier.
            title: Target document title.
            kind: Artifact kind ('report' or 'data_table').

        Returns:
            Export result metadata dictionary.
        """
        ...

    async def suggest_reports(self, notebook_id: str) -> list[dict[str, Any]]:
        """Ask Gemini Notebook for AI-suggested report topics.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            List of suggested report dictionaries.
        """
        ...

    async def retry_remote_artifact(self, notebook_id: str, artifact_id: str) -> dict[str, Any]:
        """Retry a failed remote artifact generation directly on Gemini Notebook.

        Args:
            notebook_id: Notebook identifier.
            artifact_id: Failed remote artifact identifier.

        Returns:
            Status summary dictionary.
        """
        ...

    async def add_url_source(self, notebook_id: str, url: str, title: str | None = None) -> dict[str, Any]:
        """Add a web page or YouTube URL as a source in a notebook.

        Args:
            notebook_id: Notebook identifier.
            url: Target web or YouTube URL.
            title: Optional source title override.

        Returns:
            Created source summary dictionary.
        """
        ...

    async def add_text_source(self, notebook_id: str, title: str, content: str) -> dict[str, Any]:
        """Add pasted plain text as a source in a notebook.

        Args:
            notebook_id: Notebook identifier.
            title: Source title.
            content: Plain text body.

        Returns:
            Created source summary dictionary.
        """
        ...

    async def research_sources(self, notebook_id: str, query: str, mode: str = "fast") -> dict[str, Any]:
        """Run web discovery research in a notebook and return candidate sources.

        Args:
            notebook_id: Notebook identifier.
            query: Search topic or research question.
            mode: Discovery mode ('fast' or 'deep').

        Returns:
            Research task dictionary with task_id, summary, and discovered sources.
        """
        ...

    async def import_research_sources(
        self, notebook_id: str, task_id: str, sources: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Import selected discovered research sources into a notebook.

        Args:
            notebook_id: Notebook identifier.
            task_id: Research task identifier.
            sources: List of source dicts (`url`, `title`).

        Returns:
            List of imported source records.
        """
        ...

    async def configure_chat(
        self,
        notebook_id: str,
        goal: str = "default",
        response_length: str = "default",
        custom_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Configure chat persona goal and response length for a notebook.

        Args:
            notebook_id: Notebook identifier.
            goal: Chat goal ('default', 'learning_guide', 'custom').
            response_length: Response length ('default', 'shorter', 'longer').
            custom_prompt: Custom system instructions when goal is 'custom'.

        Returns:
            Applied configuration dictionary.
        """
        ...

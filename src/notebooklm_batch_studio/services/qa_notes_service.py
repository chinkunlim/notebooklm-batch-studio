"""Core service for Gemini Notebook exploratory Q&A, structured Markdown notes, and tags (SPEC-011)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError, SourceLimitExceededError
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.domain.notebooklm_protocol import NotebookLMClientProtocol
from notebooklm_batch_studio.domain.qa_notes import (
    CourseQANote,
    MasteryStatus,
    NoteScene,
    QANoteRepositoryProtocol,
)
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol
from notebooklm_batch_studio.services.converters.note_pdf_renderer import render_markdown_to_pdf
from notebooklm_batch_studio.services.qa_notes_formatter import (
    SCENE_TAG_MAP,
    SUMMARY_PROMPT,
    build_hierarchical_tags,
    extract_tags_from_markdown,
    extract_title_from_markdown,
    note_to_dict,
    render_note_file_text,
    slugify_note_title,
    sync_mastery_tag,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AskOptions:
    """Optional parameters for a scoped Q&A query.

    Attributes:
        lecture_no: Optional lecture sequence number to focus on.
        conversation_id: Existing conversation ID to continue, or None.
        use_web_search: Whether to also run web search for supplemental references.
    """

    lecture_no: int | None = None
    conversation_id: str | None = None
    use_web_search: bool = False


class QANotesService:
    """Service coordinating NotebookLM Q&A sessions, Markdown notes, tags, and source pushing."""

    web_search_fn: Callable[[str], Awaitable[list[dict[str, str]]]] | None = None

    def __init__(
        self,
        course_repo: CourseRepositoryProtocol,
        notes_repo: QANoteRepositoryProtocol,
        notebooklm_client: NotebookLMClientProtocol,
        config: AppConfig,
    ) -> None:
        """Initialize QANotesService with repositories, NotebookLM client, and config.

        Args:
            course_repo: Course repository.
            notes_repo: Q&A note repository.
            notebooklm_client: NotebookLM client protocol implementation.
            config: Application configuration.
        """
        self.course_repo = course_repo
        self.notes_repo = notes_repo
        self.notebooklm_client = notebooklm_client
        self.config = config

    def _require_course(self, course_code: str) -> Course:
        """Load a course or raise CourseNotFoundError.

        Args:
            course_code: Course identifier.

        Returns:
            Domain Course entity.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")
        return course

    def _resolve_source_ids(self, course: Course, lecture_no: int | None) -> list[str] | None:
        """Map an optional lecture number to its uploaded Gemini Notebook source_id.

        Args:
            course: Registered Course entity.
            lecture_no: Optional lecture sequence number.

        Returns:
            Single-item source_id list, or None to query the entire notebook.
        """
        if lecture_no is None:
            return None
        lec = next((item for item in course.lectures if item.no == lecture_no), None)
        if lec is None or not lec.source_id:
            return None
        return [lec.source_id]

    def _notes_dir(self, course_code: str) -> Path:
        """Return the directory path for course Q&A Markdown notes.

        Args:
            course_code: Course identifier.

        Returns:
            Directory path under study directory or DATA_DIR.
        """
        course = self.course_repo.get_course(course_code)
        if course and course.study_dir:
            path = Path(course.study_dir) / "03 Notes" / "QA_Notes"
        else:
            path = self.config.courses_output_dir / course_code / "notes"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_note_markdown(self, note: CourseQANote) -> Path:
        """Persist or overwrite the Markdown file for a CourseQANote on disk.

        Args:
            note: Saved CourseQANote entity.

        Returns:
            Path to the written `.md` file.
        """
        directory = self._notes_dir(note.course_code)
        existing = list(directory.glob(f"{note.id}*.md"))
        target = existing[0] if existing else (directory / f"{note.id}_{slugify_note_title(note.title)}.md")
        target.write_text(render_note_file_text(note), encoding="utf-8")
        return target

    async def ask(
        self,
        course_code: str,
        question: str,
        options: AskOptions | None = None,
        lecture_no: int | None = None,
    ) -> dict[str, Any]:
        """Ask Gemini Notebook a question scoped to all or one lecture source.

        Args:
            course_code: Course identifier.
            question: Question text.
            options: Optional lecture scope, conversation ID, and web search toggle.
            lecture_no: Legacy lecture number keyword argument (used when options is None).

        Returns:
            Dictionary containing `answer`, `conversation_id`, `references`, and `web_references`.
        """
        opts = options or AskOptions(lecture_no=lecture_no)
        course = self._require_course(course_code)
        if not course.notebook_id:
            raise ValueError(f"Course {course_code} has no linked Gemini Notebook")
        source_ids = self._resolve_source_ids(course, opts.lecture_no)
        logger.info(
            "Q&A ask for %s (lecture=%s, conv=%s, web=%s)",
            course_code,
            opts.lecture_no,
            opts.conversation_id,
            opts.use_web_search,
        )
        qa_coro = self.notebooklm_client.ask_qa(
            course.notebook_id, question, source_ids=source_ids, conversation_id=opts.conversation_id
        )
        if opts.use_web_search and self.web_search_fn is not None:
            res, web_refs = await asyncio.gather(qa_coro, self.web_search_fn(question))
        else:
            res = await qa_coro
            web_refs = []
        return {**res, "web_references": web_refs}

    async def summarize_and_format(
        self,
        course_code: str,
        conversation_id: str,
        lecture_no: int | None = None,
        scene: str = NoteScene.CHAT_DRAWER.value,
    ) -> dict[str, Any]:
        """Request NotebookLM to format the active conversation into structured Markdown.

        Args:
            course_code: Course identifier.
            conversation_id: Active NotebookLM conversation identifier.
            lecture_no: Optional lecture number for tag metadata.
            scene: Origin scene (`chat_drawer`, `study_tab`, `quiz_explain`).

        Returns:
            Dictionary with formatted `markdown`, extracted `title`, and `tags`.
        """
        course = self._require_course(course_code)
        if not course.notebook_id:
            raise ValueError(f"Course {course_code} has no linked Gemini Notebook")
        lec_slug = f"L{lecture_no:02d}" if lecture_no is not None else "ALL"
        prompt = SUMMARY_PROMPT.format(
            course_code=course_code,
            lecture_slug=lec_slug,
            scene_tag=SCENE_TAG_MAP.get(scene, "類型/自主探討"),
        )
        source_ids = self._resolve_source_ids(course, lecture_no)
        res = await self.notebooklm_client.ask_qa(
            course.notebook_id, prompt, source_ids=source_ids, conversation_id=conversation_id
        )
        md_text = res["answer"].strip()
        ai_tags = extract_tags_from_markdown(md_text)
        tags = build_hierarchical_tags(course_code, lecture_no, scene, ai_tags)
        return {
            "title": extract_title_from_markdown(md_text),
            "markdown": md_text,
            "tags": tags,
            "conversation_id": res.get("conversation_id") or conversation_id,
        }

    def _build_note_entity(
        self, course_code: str, title: str, content_markdown: str, options: dict[str, Any]
    ) -> CourseQANote:
        """Assemble a CourseQANote domain entity from save options.

        Args:
            course_code: Course identifier.
            title: Note heading title.
            content_markdown: Markdown body text.
            options: Extra save metadata (`lecture_no`, `tags`, `source_scene`, `personal_memo`, `note_id`).

        Returns:
            Constructed CourseQANote ready for persistence.
        """
        lecture_no = options.get("lecture_no")
        scene = str(options.get("source_scene") or NoteScene.CHAT_DRAWER.value)
        note_id = str(options.get("note_id") or f"note-{uuid4().hex[:10]}")
        extra_tags = list(options.get("tags") or []) + extract_tags_from_markdown(content_markdown)
        existing = self.notes_repo.get_note(note_id)
        mastery = existing.mastery_status if existing else MasteryStatus.NEEDS_REVIEW.value
        tags = sync_mastery_tag(build_hierarchical_tags(course_code, lecture_no, scene, extra_tags), mastery)
        return CourseQANote(
            id=note_id,
            course_code=course_code,
            lecture_no=lecture_no,
            title=title.strip() or extract_title_from_markdown(content_markdown),
            content_markdown=content_markdown,
            personal_memo=options.get("personal_memo"),
            tags=tags,
            source_scene=scene,
            mastery_status=mastery,
            is_uploaded_as_source=existing.is_uploaded_as_source if existing else False,
            uploaded_source_id=existing.uploaded_source_id if existing else None,
        )

    def save_note(
        self, course_code: str, title: str, content_markdown: str, **options: Any
    ) -> dict[str, Any]:
        """Save a Q&A Markdown note to SQLite and `$DATA_DIR/output/courses/<code>/notes/`.

        Args:
            course_code: Course identifier.
            title: Note heading title.
            content_markdown: Note body in Markdown.
            **options: Optional `lecture_no`, `tags`, `source_scene`, `personal_memo`, `note_id`.

        Returns:
            Serialized note dictionary.
        """
        self._require_course(course_code)
        entity = self._build_note_entity(course_code, title, content_markdown, options)
        saved = self.notes_repo.upsert_note(entity)
        self._write_note_markdown(saved)
        logger.info("Saved Q&A note %s for course %s", saved.id, course_code)
        return note_to_dict(saved)

    def list_notes(
        self,
        course_code: str,
        tag: str | None = None,
        lecture_no: int | None = None,
        mastery: str | None = None,
    ) -> list[dict[str, Any]]:
        """List saved Q&A notes for a course with optional tag/lecture/mastery filters.

        Args:
            course_code: Course identifier (or `*` for all courses).
            tag: Optional substring/exact tag filter (e.g. `L03`, `進化論`).
            lecture_no: Optional lecture sequence filter.
            mastery: Optional mastery filter.

        Returns:
            List of serialized note dictionaries.
        """
        target_course = None if course_code == "*" else course_code
        notes = self.notes_repo.list_notes(target_course, lecture_no=lecture_no, mastery_status=mastery)
        if tag:
            needle = tag.lstrip("#").strip().lower()
            notes = [n for n in notes if any(needle in t.lower() for t in n.tags)]
        return [note_to_dict(n) for n in notes]

    def toggle_mastery(self, note_id: str, status: str) -> dict[str, Any]:
        """Update a note's mastery status and sync the tag inside its Markdown file.

        Args:
            note_id: Note identifier.
            status: New mastery status (`needs_review` or `mastered`).

        Returns:
            Updated note dictionary.
        """
        note = self.notes_repo.get_note(note_id)
        if note is None:
            raise ValueError(f"Note not found: {note_id}")
        valid_status = MasteryStatus(status).value
        note.mastery_status = valid_status
        note.tags = sync_mastery_tag(note.tags, valid_status)
        saved = self.notes_repo.upsert_note(note)
        self._write_note_markdown(saved)
        return note_to_dict(saved)

    def update_memo(self, note_id: str, personal_memo: str) -> dict[str, Any]:
        """Update a note's personal memo and rewrite its Markdown file.

        Args:
            note_id: Note identifier.
            personal_memo: Personal annotation text.

        Returns:
            Updated note dictionary.
        """
        note = self.notes_repo.get_note(note_id)
        if note is None:
            raise ValueError(f"Note not found: {note_id}")
        note.personal_memo = personal_memo.strip() or None
        saved = self.notes_repo.upsert_note(note)
        self._write_note_markdown(saved)
        return note_to_dict(saved)

    async def _check_upload_capacity(self, course: Course) -> None:
        """Guard against exceeding Gemini Notebook's 50-source limit before pushing notes.

        Args:
            course: Domain Course entity.
        """
        if not course.notebook_id:
            raise ValueError(f"Course {course.code} has no linked Gemini Notebook")
        limit = await self.notebooklm_client.get_source_limit()
        if limit is None:
            return
        sources = await self.notebooklm_client.list_sources(course.notebook_id)
        if len(sources) >= limit:
            raise SourceLimitExceededError(
                f"Notebook for {course.code} already has {len(sources)}/{limit} sources; "
                "use bundle_notes_to_source or remove old sources first"
            )

    async def push_note_to_source(self, course_code: str, note_id: str) -> dict[str, Any]:
        """Render a single note as PDF and upload it to Gemini Notebook as a source.

        Args:
            course_code: Course identifier.
            note_id: Note identifier.

        Returns:
            Updated note dictionary with `uploaded_source_id`.
        """
        course = self._require_course(course_code)
        note = self.notes_repo.get_note(note_id)
        if note is None or note.course_code != course_code:
            raise ValueError(f"Note {note_id} not found for course {course_code}")
        await self._check_upload_capacity(course)

        pdf_dir = self.config.courses_input_dir / course_code / "_uploaded_sources"
        pdf_path = pdf_dir / f"{note.id}_{slugify_note_title(note.title)}.pdf"
        render_markdown_to_pdf(note.title, render_note_file_text(note), pdf_path)

        assert course.notebook_id is not None
        source_id = await self.notebooklm_client.upload_source(course.notebook_id, str(pdf_path))
        await self.notebooklm_client.wait_source_ready(course.notebook_id, source_id)
        note.is_uploaded_as_source = True
        note.uploaded_source_id = source_id
        return note_to_dict(self.notes_repo.upsert_note(note))

    def _collect_bundle_notes(self, course_code: str, note_ids: list[str]) -> tuple[list[CourseQANote], str]:
        """Load valid notes and combine them into one Markdown string for PDF rendering.

        Args:
            course_code: Course identifier.
            note_ids: Note IDs to combine.

        Returns:
            Tuple of `(included notes, combined Markdown text)`.
        """
        parts: list[str] = []
        included: list[CourseQANote] = []
        for nid in note_ids:
            note = self.notes_repo.get_note(nid)
            if note is not None and note.course_code == course_code:
                included.append(note)
                memo = f"\n\n個人備忘：{note.personal_memo}" if note.personal_memo else ""
                parts.append(f"# {note.title}\n\n{note.content_markdown}{memo}\n\n---")
        if not included:
            raise ValueError("No valid notes matched the provided note_ids")
        return included, "\n\n".join(parts)

    async def bundle_notes_to_source(
        self, course_code: str, note_ids: list[str], title: str
    ) -> dict[str, Any]:
        """Bundle multiple Q&A notes into a single PDF and upload once to save source quota.

        Args:
            course_code: Course identifier.
            note_ids: List of note IDs to combine.
            title: Title for the bundled PDF document.

        Returns:
            Dictionary containing `source_id`, `bundled_count`, and `filename`.
        """
        course = self._require_course(course_code)
        if not note_ids:
            raise ValueError("Select at least one note to bundle")
        await self._check_upload_capacity(course)

        included, combined_md = self._collect_bundle_notes(course_code, note_ids)
        pdf_dir = self.config.courses_input_dir / course_code / "_uploaded_sources"
        pdf_path = pdf_dir / f"bundle_{slugify_note_title(title)}_{uuid4().hex[:6]}.pdf"
        render_markdown_to_pdf(title, combined_md, pdf_path)

        assert course.notebook_id is not None
        source_id = await self.notebooklm_client.upload_source(course.notebook_id, str(pdf_path))
        await self.notebooklm_client.wait_source_ready(course.notebook_id, source_id)
        for note in included:
            note.is_uploaded_as_source = True
            note.uploaded_source_id = source_id
            self.notes_repo.upsert_note(note)
        return {
            "code": course_code,
            "source_id": source_id,
            "bundled_count": len(included),
            "filename": pdf_path.name,
        }

    def delete_note(self, note_id: str) -> bool:
        """Delete a note record and remove its local Markdown file if present.

        Args:
            note_id: Note identifier.

        Returns:
            True if deleted, False if missing.
        """
        note = self.notes_repo.get_note(note_id)
        if note is None:
            return False
        for md_file in self._notes_dir(note.course_code).glob(f"{note.id}*.md"):
            md_file.unlink(missing_ok=True)
        return self.notes_repo.delete_note(note_id)

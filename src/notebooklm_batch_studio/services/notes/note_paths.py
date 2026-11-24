"""Where note-studio files live, and the path-safety checks for note requests (Refs: ADR-012, ISSUE-045).

`NotePathResolver` turns a course key / chapter ID into folders under `03 Notes/NoteStudio`
(or `scratch/notes/<course_key>`), and refuses identifiers or caller-supplied paths that
would escape `DATA_DIR`, `STUDY_ROOT_DIR`, or the course's registered PDF folder.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.note_pipeline import NoteBackend
from notebooklm_batch_studio.domain.path_safety import (
    PathSafetyError,
    ensure_within_roots,
    validate_path_segment,
)
from notebooklm_batch_studio.domain.study_hierarchy import resolve_note_studio_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChapterNoteRequest:
    """Parameters for generating or rerunning one chapter's Markdown notes.

    Attributes:
        course_key: Course identifier or folder code.
        course_name: Human-readable course name filled into `{{COURSE_NAME}}`.
        chapter_id: Chapter identifier such as `ch01`.
        chapter_title: Chapter title filled into `{{CHAPTER_TITLE}}`.
        pdf_path: Optional chapter PDF path (used by `gemini_web` upload).
        backend: Generation backend (`gemini_web` default, `notebooklm` fallback).
        model: Gemini model name (e.g. `4 Argon`).
        notebook_id: Target NotebookLM ID when `backend == notebooklm`.
        source_ids: Single-chapter NotebookLM source IDs when `backend == notebooklm`.
        steps_override: Optional subset of step IDs for single-module rerun.
        study_dir: Optional course study directory (`<study_root>/<term>/<subject>`).
    """

    course_key: str
    course_name: str
    chapter_id: str
    chapter_title: str = ""
    pdf_path: Path | None = None
    backend: NoteBackend = NoteBackend.GEMINI_WEB
    model: str = "4 Argon"
    notebook_id: str = ""
    source_ids: list[str] = field(default_factory=list)
    steps_override: list[str] | None = None
    study_dir: Path | None = None


class NotePathResolver:
    """Resolves and validates note-studio folders and caller-supplied paths."""

    def __init__(
        self,
        config: AppConfig,
        study_dir_resolver: Callable[[str], Path | None] | None = None,
        source_dir_resolver: Callable[[str], Path | None] | None = None,
    ) -> None:
        """Initialize the resolver.

        Args:
            config: Immutable application configuration.
            study_dir_resolver: Optional callback resolving `course_key -> study_dir`.
            source_dir_resolver: Optional callback resolving `course_key -> registered PDF folder`.
        """
        self.config = config
        self._study_dir_resolver = study_dir_resolver
        self._source_dir_resolver = source_dir_resolver

    def notes_course_dir(self, course_key: str, study_dir: Path | None = None) -> Path:
        """Return `<study_dir>/03 Notes/NoteStudio`, or `<scratch_dir>/notes/<course_key>` if unlinked.

        Args:
            course_key: Course identifier.
            study_dir: Optional explicit course study directory.

        Returns:
            Path inside `03 Notes/NoteStudio`, or `scratch/notes/<course_key>` when no study_dir exists.
        """
        validate_path_segment(course_key, "course_key")
        if study_dir is not None:
            study_dir = self.checked_study_dir(study_dir)
        resolved = study_dir or (self._study_dir_resolver(course_key) if self._study_dir_resolver else None)
        if resolved is not None:
            return resolve_note_studio_dir(resolved)
        return self.config.scratch_dir / "notes" / course_key

    def checked_study_dir(self, study_dir: Path) -> Path:
        """Require a caller-supplied study folder to sit inside `DATA_DIR` or `STUDY_ROOT_DIR`.

        Args:
            study_dir: Caller-supplied course study directory.

        Returns:
            The resolved study directory.

        Raises:
            PathSafetyError: The folder is outside both roots.
        """
        return ensure_within_roots(study_dir, (self.config.data_dir, self.config.study_root_dir), "study_dir")

    def checked_pdf_path(self, course_key: str, pdf_path: Path) -> Path:
        """Require a chapter PDF to be a `.pdf` inside the app's folders or the course's PDF folder.

        Args:
            course_key: Course identifier used to look up the registered PDF folder.
            pdf_path: Caller-supplied chapter PDF path.

        Returns:
            The resolved PDF path.

        Raises:
            PathSafetyError: Not a `.pdf`, or outside every allowed folder.
        """
        if pdf_path.suffix.lower() != ".pdf":
            raise PathSafetyError(f"pdf_path 必須是 .pdf 檔案：{pdf_path.name}")
        source_dir = self._source_dir_resolver(course_key) if self._source_dir_resolver else None
        roots = (self.config.data_dir, self.config.study_root_dir, source_dir)
        return ensure_within_roots(pdf_path, roots, "pdf_path")

    def validated_request(self, request: ChapterNoteRequest) -> ChapterNoteRequest:
        """Validate identifiers and paths of a chapter request before anything touches disk.

        Args:
            request: Raw chapter note request from HTTP or MCP.

        Returns:
            Copy of the request with resolved, checked paths.

        Raises:
            PathSafetyError: Any identifier or path is unsafe.
        """
        validate_path_segment(request.course_key, "course_key")
        validate_path_segment(request.chapter_id, "chapter_id")
        study_dir = self.checked_study_dir(request.study_dir) if request.study_dir else None
        pdf_path = self.checked_pdf_path(request.course_key, request.pdf_path) if request.pdf_path else None
        return replace(request, study_dir=study_dir, pdf_path=pdf_path)

    def stitched_note_path(self, request: ChapterNoteRequest) -> Path:
        """Return the canonical stitched `.md` path for a chapter.

        Args:
            request: Chapter note generation request.

        Returns:
            Path to `<chapter_id>_<title>_學習筆記.md` inside `03 Notes/NoteStudio`.
        """
        title = request.chapter_title.strip() or request.chapter_id
        safe_title = title.replace("/", "_").replace("\\", "_")
        notes_dir = self.notes_course_dir(request.course_key, request.study_dir)
        return notes_dir / f"{request.chapter_id}_{safe_title}_學習筆記.md"

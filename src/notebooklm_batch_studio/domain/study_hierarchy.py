"""Study folder hierarchy rules: `<term>/<subject>/<category>[/<subfolder>]` (ADR-011, ADR-014).

Derives canonical category names (`01 Materials`..`05 Assignments`) from `StudyLayout`,
handles legacy singular aliases, term/subject parsing, and safe path resolution.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from notebooklm_batch_studio.domain.study_layout import DEFAULT_LAYOUT, CategoryRole, StudyLayout

logger = logging.getLogger(__name__)

STUDY_CATEGORIES: tuple[str, ...] = tuple(DEFAULT_LAYOUT.names[role] for role in CategoryRole)
INPUT_SOURCE_CATEGORIES: tuple[str, ...] = (DEFAULT_LAYOUT.names[CategoryRole.HANDOUTS],)
DEFAULT_LITERATURE_CATEGORY = DEFAULT_LAYOUT.names[CategoryRole.MATERIALS]
DEFAULT_LITERATURE_SUBFOLDER = "Literature_Review"
NOTEBOOKLM_NOTES_SUBFOLDER = "NotebookLM"
QA_NOTES_SUBFOLDER = "QA_Notes"
NOTE_STUDIO_SUBFOLDER = "NoteStudio"

_TERM_SUBJECT_RE = re.compile(r"^\s*(\d{2,4}[-_]\d{1,2})\s+(.+?)\s*$")
_UNSAFE_SEGMENT_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_segment(name: str, fallback: str = "untitled") -> str:
    """Clean a single folder or path segment while preserving readable CJK/ASCII text.

    Args:
        name: Raw folder or subject name.
        fallback: Fallback when cleaned string is empty or traversal-like.

    Returns:
        Safe single-segment directory name.
    """
    cleaned = _UNSAFE_SEGMENT_RE.sub("_", name.strip()).strip(". ")
    if not cleaned or cleaned in (".", ".."):
        return fallback
    return cleaned


def parse_term_subject(folder_name: str, default_term: str = "general") -> tuple[str, str]:
    """Extract `(term, subject)` from a folder name like `115-1 心理學研究法`.

    Args:
        folder_name: Existing course folder name or display title.
        default_term: Term folder to use when no `<year>-<semester>` prefix is present.

    Returns:
        Tuple of `(term, subject)`.
    """
    match = _TERM_SUBJECT_RE.match(folder_name or "")
    if match:
        term = sanitize_segment(match.group(1).replace("_", "-"), default_term)
        subject = sanitize_segment(match.group(2), "course")
        return term, subject
    return sanitize_segment(default_term, "general"), sanitize_segment(folder_name or "course", "course")


def resolve_course_study_dir(study_root: Path, term: str, subject: str, fallback_code: str) -> Path:
    """Resolve `<study_root>/<term>/<subject>` for a course.

    Args:
        study_root: Root directory for unified study folders.
        term: Academic term string (e.g. `115-1`).
        subject: Subject name (e.g. `心理學研究法`).
        fallback_code: Course code used if `subject` is empty.

    Returns:
        Resolved course study directory path.
    """
    safe_term = sanitize_segment(term or "general", "general")
    safe_subject = sanitize_segment(subject or fallback_code, fallback_code or "course")
    return study_root / safe_term / safe_subject


def resolve_category_dir(
    course_dir: Path,
    category: str,
    subfolder: str = "",
    layout: StudyLayout = DEFAULT_LAYOUT,
) -> Path:
    """Resolve `<course_dir>/<category>[/<subfolder>]` safely inside `course_dir`.

    Args:
        course_dir: Root directory of the course.
        category: Target category name or alias (defaults to MATERIALS role if unrecognized).
        subfolder: Optional relative subfolder path (supports nested `/` segments).
        layout: Study layout defining role names and aliases.

    Returns:
        Resolved directory path under `course_dir`.
    """
    role = layout.role_of(category) or CategoryRole.MATERIALS
    target = layout.primary_dir(course_dir, role)
    if subfolder:
        parts = [sanitize_segment(p, "") for p in subfolder.replace("\\", "/").split("/")]
        for part in parts:
            if part:
                target = target / part
    return target


def resolve_literature_dir(
    course_dir: Path,
    category: str = DEFAULT_LITERATURE_CATEGORY,
    subfolder: str = DEFAULT_LITERATURE_SUBFOLDER,
) -> Path:
    """Resolve the target directory for downloaded literature PDFs of a course.

    Args:
        course_dir: Course study directory.
        category: Target study category (defaults to `DEFAULT_LITERATURE_CATEGORY`).
        subfolder: Target subfolder (default `Literature_Review`).

    Returns:
        Directory path where literature PDFs and reports are stored.
    """
    return resolve_category_dir(course_dir, category, subfolder)


def resolve_notebooklm_notes_dir(course_dir: Path) -> Path:
    """Resolve `<course_dir>/03 Notes/NotebookLM` for generated artifacts.

    Args:
        course_dir: Course study directory.

    Returns:
        Directory path for NotebookLM generated study outputs.
    """
    return resolve_category_dir(course_dir, "03 Notes", NOTEBOOKLM_NOTES_SUBFOLDER)


def resolve_qa_notes_dir(course_dir: Path) -> Path:
    """Resolve `<course_dir>/03 Notes/QA_Notes` for SPEC-011 exploration notes.

    Args:
        course_dir: Course study directory.

    Returns:
        Directory path for saved Q&A markdown notes.
    """
    return resolve_category_dir(course_dir, "03 Notes", QA_NOTES_SUBFOLDER)


def resolve_note_studio_dir(course_dir: Path) -> Path:
    """Resolve `<course_dir>/03 Notes/NoteStudio` for modular Markdown notes.

    Args:
        course_dir: Course study directory.

    Returns:
        Directory path for modular `.md` notes, modules, and version archives.
    """
    return resolve_category_dir(course_dir, "03 Notes", NOTE_STUDIO_SUBFOLDER)


def ensure_course_study_tree(course_dir: Path, layout: StudyLayout = DEFAULT_LAYOUT) -> None:
    """Create the standard five category directories under a course study directory.

    Args:
        course_dir: Course study directory to initialize.
        layout: Study layout defining category names and aliases.
    """
    layout.ensure_tree(course_dir)


def resolve_lecture_pdf_path(source_dir: str | Path, filename: str, relative_path: str = "") -> Path:
    """Resolve the filesystem path of a lecture PDF, honoring nested `relative_path` if present.

    Args:
        source_dir: Course root directory.
        filename: PDF filename.
        relative_path: Optional relative path inside `source_dir`.

    Returns:
        Path to the lecture PDF file.
    """
    base = Path(source_dir)
    if relative_path:
        candidate = base / relative_path
        if candidate.is_file():
            return candidate
    return base / filename


def resolve_course_output_root(fallback_output_root: Path, course_code: str, study_dir: str = "") -> Path:
    """Resolve the NotebookLM output root for a course.

    When `study_dir` is configured, returns `<study_dir>/03 Notes/NotebookLM`; otherwise
    returns `<fallback_output_root>/<course_code>`.

    Args:
        fallback_output_root: Fallback output root when `study_dir` is empty.
        course_code: Course identifier.
        study_dir: Optional unified study directory path.

    Returns:
        Course output root directory.
    """
    if study_dir:
        return resolve_notebooklm_notes_dir(Path(study_dir))
    return fallback_output_root / course_code


@dataclass(frozen=True)
class CourseMigrationTarget:
    """Where one course lands after migrating into `<study_root>/<term>/<subject>`.

    Attributes:
        code: Course code.
        term: Resolved academic term.
        subject: Resolved subject name.
        study_dir: New unified study directory.
        notes_dir: New `<study_dir>/03 Notes/NotebookLM` directory.
    """

    code: str
    term: str
    subject: str
    study_dir: Path
    notes_dir: Path

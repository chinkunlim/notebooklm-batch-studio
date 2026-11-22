"""Study folder hierarchy rules: `<term>/<subject>/<category>[/<subfolder>]` (ADR-011).

Defines the canonical five categories (`01 Material`, `02 Handout`, `03 Notes`, `04 Homework`,
`05 Assignments`), term/subject parsing from legacy course names, and safe path resolution.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

STUDY_CATEGORIES: tuple[str, ...] = (
    "01 Material",
    "02 Handout",
    "03 Notes",
    "04 Homework",
    "05 Assignments",
)
INPUT_SOURCE_CATEGORIES: tuple[str, ...] = ("01 Material", "02 Handout")
DEFAULT_LITERATURE_CATEGORY = "01 Material"
DEFAULT_LITERATURE_SUBFOLDER = "Literature_Review"
NOTEBOOKLM_NOTES_SUBFOLDER = "NotebookLM"
QA_NOTES_SUBFOLDER = "QA_Notes"

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


def resolve_category_dir(course_dir: Path, category: str, subfolder: str = "") -> Path:
    """Resolve `<course_dir>/<category>[/<subfolder>]` safely inside `course_dir`.

    Args:
        course_dir: Root directory of the course.
        category: One of `STUDY_CATEGORIES` (defaults to `01 Material` if invalid).
        subfolder: Optional relative subfolder path (supports nested `/` segments).

    Returns:
        Resolved directory path under `course_dir`.
    """
    chosen = category if category in STUDY_CATEGORIES else DEFAULT_LITERATURE_CATEGORY
    target = course_dir / chosen
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
        category: Target study category (default `01 Material`).
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


def ensure_course_study_tree(course_dir: Path) -> None:
    """Create the standard five category directories under a course study directory.

    Args:
        course_dir: Course study directory to initialize.
    """
    for category in STUDY_CATEGORIES:
        (course_dir / category).mkdir(parents=True, exist_ok=True)
    logger.debug("Ensured standard study categories under %s", course_dir)


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


def resolve_course_output_root(
    default_courses_output_dir: Path, course_code: str, study_dir: str = ""
) -> Path:
    """Resolve the NotebookLM output root for a course.

    When `study_dir` is configured, returns `<study_dir>/03 Notes/NotebookLM`; otherwise
    returns the legacy `<courses_output_dir>/<course_code>`.

    Args:
        default_courses_output_dir: Legacy `<data_dir>/output/courses` root.
        course_code: Course identifier.
        study_dir: Optional unified study directory path.

    Returns:
        Course output root directory.
    """
    if study_dir:
        return resolve_notebooklm_notes_dir(Path(study_dir))
    return default_courses_output_dir / course_code

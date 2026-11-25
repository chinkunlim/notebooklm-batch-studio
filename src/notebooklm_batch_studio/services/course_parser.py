"""Course parser: scans course directories, infers codes, extracts lectures, and manages course.toml."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

import tomli

from notebooklm_batch_studio.domain.course_identity import (
    TERM_PATTERN,
    make_course_code,
    parse_course_folder,
    split_course_code,
)
from notebooklm_batch_studio.domain.models import Course, Lecture, ProfileName
from notebooklm_batch_studio.domain.study_hierarchy import parse_term_subject
from notebooklm_batch_studio.domain.study_layout import DEFAULT_LAYOUT, CategoryRole, StudyLayout
from notebooklm_batch_studio.domain.textbook_sections import TEXTBOOK_MARKER

logger = logging.getLogger(__name__)


def parse_course_folder_name(folder_name: str) -> tuple[str, str]:
    """Infer course code and course title from a folder name.

    If an alphanumeric prefix contains letters (e.g. 'BIO101', 'CS-50'), it is treated
    as the course code. If the prefix is purely numeric or a semester tag (e.g. '115-1'),
    it is not a unique course code on its own, so the full folder name is used to prevent
    collision across different courses in the same semester. Refs: ISSUE-037

    Args:
        folder_name: The basename of the course folder.

    Returns:
        A tuple of (course_code, course_name).
    """
    clean_name = folder_name.strip()
    match = re.match(r"^([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)[\s_]+(.+)$", clean_name)
    if not match:
        match = re.match(r"^([A-Za-z0-9]+)[\s_\-]+(.+)$", clean_name)
    if match:
        code_candidate = match.group(1).strip()
        name_candidate = match.group(2).strip()
        # Pure numeric-hyphen patterns (like '115-1', '114-2', '2026-1') represent terms/semesters,
        # not unique subject codes. Use full folder name to avoid collision. Refs: ISSUE-037
        if re.match(r"^\d+(?:-\d+)*$", code_candidate):
            return clean_name, clean_name
        return code_candidate.upper(), name_candidate
    return clean_name, clean_name


def parse_lecture_filename(filename: str, fallback_no: int) -> tuple[int, str]:
    """Infer sequence number and topic name from a lecture PDF filename.

    Args:
        filename: Name of the PDF file.
        fallback_no: Default lecture sequence number.

    Returns:
        A tuple of (lecture_number, topic_name).
    """
    stem = Path(filename).stem
    match = re.match(r"^(?:Lecture\s*|Chapter\s*|Ch\s*)?(\d+)[\s_\-]*(.*)$", stem, re.IGNORECASE)
    if match:
        no = int(match.group(1))
        topic = match.group(2).strip() or f"Lecture {no}"
        return no, topic
    return fallback_no, stem


def compute_pdf_sha256(pdf_path: Path) -> str:
    """Compute the SHA-256 cryptographic digest of a PDF file.

    Args:
        pdf_path: Path to the target PDF file.

    Returns:
        Hexadecimal SHA-256 hash string.
    """
    hasher = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _is_visible_pdf(path: Path) -> bool:
    """Return True when `path` is a non-hidden PDF file.

    Args:
        path: Candidate filesystem path.

    Returns:
        True for visible `.pdf` files.
    """
    return path.is_file() and path.suffix.lower() == ".pdf" and not path.name.startswith(".")


def _find_candidate_pdfs(
    course_dir: Path, layout: StudyLayout = DEFAULT_LAYOUT
) -> list[tuple[Path, str, str]]:
    """Find candidate PDF files in a course directory (supporting study hierarchy).

    When the directory uses the 5-category study layout (recognizing plural names and legacy
    singular aliases), recursively scans only the `HANDOUTS` role directory (plus top-level PDFs)
    while ignoring `MATERIALS`, `NOTES`, `HOMEWORK`, and `ASSIGNMENTS`. Otherwise scans top-level PDFs.

    Args:
        course_dir: Root directory of the course.
        layout: Study category layout configuration.

    Returns:
        Sorted list of `(pdf_path, category, relative_path)` tuples.
    """
    has_study_layout = any(layout.category_dirs(course_dir, role) for role in CategoryRole)
    top_level = [(p, "", p.name) for p in course_dir.iterdir() if _is_visible_pdf(p)]
    if not has_study_layout:
        return sorted(top_level, key=lambda item: item[2].lower())

    handouts = _role_pdfs(course_dir, layout.category_dirs(course_dir, CategoryRole.HANDOUTS), recursive=True)
    if not handouts:  # Refs: SPEC-018 — textbook chapters are the lecture source when 02 Handouts is empty
        handouts = _role_pdfs(course_dir, textbook_chapter_dirs(course_dir, layout), recursive=False)
    candidates = top_level + handouts
    candidates.sort(key=lambda item: item[2].lower())
    return candidates


def textbook_chapter_dirs(course_dir: Path, layout: StudyLayout = DEFAULT_LAYOUT) -> list[Path]:
    """Return `01 Materials` subfolders marked with `.textbook.json` (split textbook chapters).

    Args:
        course_dir: Course study directory.
        layout: Study category layout configuration.

    Returns:
        Marked chapter folders, sorted.
    """
    found = {
        marker.parent
        for mat_dir in layout.category_dirs(course_dir, CategoryRole.MATERIALS)
        for marker in mat_dir.rglob(TEXTBOOK_MARKER)
        if marker.is_file() and not marker.is_symlink()
    }
    return sorted(found)


def _role_pdfs(course_dir: Path, folders: list[Path], recursive: bool) -> list[tuple[Path, str, str]]:
    """List visible PDFs in `folders` as `(path, top-level category name, course-relative path)`.

    Args:
        course_dir: Course study directory.
        folders: Folders to scan.
        recursive: Whether to include subfolders.

    Returns:
        Candidate tuples.
    """
    out: list[tuple[Path, str, str]] = []
    for folder in folders:
        for p in folder.rglob("*") if recursive else folder.iterdir():
            if _is_visible_pdf(p):
                rel = p.relative_to(course_dir).as_posix()
                out.append((p, rel.split("/", 1)[0], rel))
    return out


def _collect_unique_lectures(course_dir: Path, layout: StudyLayout = DEFAULT_LAYOUT) -> list[Lecture]:
    """Scan and deduplicate PDF files in a course directory.

    Args:
        course_dir: Directory containing lecture PDF files.
        layout: Study category layout configuration.

    Returns:
        List of deduplicated Lecture domain objects.
    """
    candidates = _find_candidate_pdfs(course_dir, layout=layout)
    lectures: list[Lecture] = []
    seen_hashes: set[str] = set()

    for idx, (pdf_path, category, rel_path) in enumerate(candidates, start=1):
        sha256_hash = compute_pdf_sha256(pdf_path)
        if sha256_hash in seen_hashes:
            logger.warning("Duplicate PDF detected (same content): %s, skipping.", pdf_path.name)
            continue
        seen_hashes.add(sha256_hash)

        no, topic = parse_lecture_filename(pdf_path.name, fallback_no=idx)
        lectures.append(
            Lecture(
                no=no,
                topic=topic,
                filename=pdf_path.name,
                sha256=sha256_hash,
                category=category,
                relative_path=rel_path,
            )
        )

    lectures.sort(key=lambda lec: lec.no)
    return lectures


def _resolve_course_identity(
    course_dir: Path, custom_code: str | None, explicit_term: str
) -> tuple[str, str, str, str, str]:
    """Infer course code, display name, term, subject, and course_no from directory metadata.

    Args:
        course_dir: Root directory of the course.
        custom_code: Optional explicit course code override.
        explicit_term: Optional semester term override (e.g. '115-1').

    Returns:
        Tuple of `(code, name, term, subject, course_no)`.
    """
    parent_term = course_dir.parent.name.replace("_", "-")
    resolved_term = explicit_term.strip().replace("_", "-")
    if not resolved_term and TERM_PATTERN.match(parent_term):
        resolved_term = parent_term

    folder_info = parse_course_folder(course_dir.name)
    if folder_info.is_course:
        inferred_name = folder_info.name
        course_no = folder_info.course_no
        inferred_code = make_course_code(resolved_term, course_no) if resolved_term else course_no
        subject = inferred_name
    else:
        inferred_code, inferred_name = parse_course_folder_name(course_dir.name)
        course_no = ""
        parsed_term, parsed_subject = parse_term_subject(course_dir.name)
        resolved_term = resolved_term or parsed_term
        subject = course_dir.name if TERM_PATTERN.match(parent_term) else (parsed_subject or inferred_name)

    code = custom_code or inferred_code
    split_term, split_no = split_course_code(code)
    if split_term and not course_no:
        course_no = split_no
        resolved_term = resolved_term or split_term
    return code, inferred_name, resolved_term, subject, course_no


def scan_course_directory(
    course_dir: Path, custom_code: str | None = None, term: str = "", layout: StudyLayout = DEFAULT_LAYOUT
) -> Course:
    """Scan lecture PDFs in a folder and construct a Course domain entity.

    Supports school folders (`CP__30000-團體諮商`) and legacy names (`BIO101 普通生物學`).

    Args:
        course_dir: Directory containing lecture PDF files.
        custom_code: Optional override for the course code.
        term: Optional semester term identifier (e.g. `115-1`).
        layout: Study category layout configuration.

    Returns:
        Constructed domain Course entity with sorted lectures.
    """
    if not course_dir.is_dir():
        raise FileNotFoundError(f"Course directory not found: {course_dir}")
    code, name, resolved_term, subject, course_no = _resolve_course_identity(course_dir, custom_code, term)
    lectures = _collect_unique_lectures(course_dir, layout=layout)
    resolved_dir = str(course_dir.resolve())
    has_study_layout = any(layout.category_dirs(course_dir, role) for role in CategoryRole)
    logger.info("Scanned course %s (%s): found %d lecture PDFs", code, name, len(lectures))
    return Course(
        code=code,
        name=name,
        source_dir=resolved_dir,
        profile=ProfileName.FULL,
        language="zh-TW",
        lectures=lectures,
        term=resolved_term,
        subject=subject,
        study_dir=resolved_dir if has_study_layout else "",
        course_no=course_no,
    )


def read_course_toml(toml_path: Path) -> dict[str, Any]:
    """Load configuration from a course.toml file.

    Args:
        toml_path: Path to the course.toml file.

    Returns:
        Dictionary of configuration keys.
    """
    if not toml_path.is_file():
        return {}
    with open(toml_path, "rb") as f:
        return tomli.load(f)


def write_course_toml(toml_path: Path, course: Course) -> None:
    """Serialize and write a Course entity to a course.toml file.

    Args:
        toml_path: Destination path for the TOML configuration file.
        course: The Course domain object.
    """
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f'name = "{course.name}"',
        f'code = "{course.code}"',
        f'source_dir = "{course.source_dir}"',
        f'profile = "{course.profile.value}"',
        f'language = "{course.language}"',
        f"watch = {'true' if course.watch else 'false'}",
        f"mock_exam_questions = {course.mock_exam_questions}",
    ]
    if course.exam_date:
        lines.append(f'exam_date = "{course.exam_date}"')
    if course.notebook_id:
        lines.append(f'notebook_id = "{course.notebook_id}"')

    lines.append("")
    for lec in course.lectures:
        lines.append("[[lectures]]")
        lines.append(f'file = "{lec.filename}"')
        lines.append(f"no = {lec.no}")
        lines.append(f'topic = "{lec.topic}"')
        lines.append(f'sha256 = "{lec.sha256}"')
        lines.append("")

    content = "\n".join(lines)
    toml_path.write_text(content, encoding="utf-8")
    logger.info("Saved course configuration to %s", toml_path)

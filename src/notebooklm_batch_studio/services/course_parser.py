"""Course parser: scans course directories, infers codes, extracts lectures, and manages course.toml."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

import tomli

from notebooklm_batch_studio.domain.models import Course, Lecture, ProfileName

logger = logging.getLogger(__name__)


def parse_course_folder_name(folder_name: str) -> tuple[str, str]:
    """Infer course code and course title from a folder name.

    Args:
        folder_name: The basename of the course folder.

    Returns:
        A tuple of (course_code, course_name).
    """
    clean_name = folder_name.strip()
    match = re.match(r"^([A-Za-z0-9]+)[\s_\-]+(.+)$", clean_name)
    if match:
        code = match.group(1).strip().upper()
        name = match.group(2).strip()
        return code, name
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
    match = re.match(r"^(?:Lecture\s*)?(\d+)[\s_\-]*(.*)$", stem, re.IGNORECASE)
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


def _collect_unique_lectures(course_dir: Path) -> list[Lecture]:
    """Scan and deduplicate PDF files in a course directory.

    Args:
        course_dir: Directory containing lecture PDF files.

    Returns:
        List of deduplicated Lecture domain objects.
    """
    pdf_files = sorted(
        [
            p
            for p in course_dir.iterdir()
            if p.is_file() and p.suffix.lower() == ".pdf" and not p.name.startswith(".")
        ],
        key=lambda p: p.name.lower(),
    )

    lectures: list[Lecture] = []
    seen_hashes: set[str] = set()

    for idx, pdf_path in enumerate(pdf_files, start=1):
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
            )
        )

    lectures.sort(key=lambda lec: lec.no)
    return lectures


def scan_course_directory(course_dir: Path, custom_code: str | None = None) -> Course:
    """Scan a folder of lecture PDFs and construct a Course domain entity.

    Args:
        course_dir: Directory containing lecture PDF files.
        custom_code: Optional override for the course code.

    Returns:
        Constructed domain Course entity with sorted lectures.

    Raises:
        FileNotFoundError: When course_dir does not exist.
    """
    if not course_dir.is_dir():
        raise FileNotFoundError(f"Course directory not found: {course_dir}")

    inferred_code, inferred_name = parse_course_folder_name(course_dir.name)
    code = custom_code or inferred_code
    lectures = _collect_unique_lectures(course_dir)

    logger.info("Scanned course %s (%s): found %d lecture PDFs", code, inferred_name, len(lectures))
    return Course(
        code=code,
        name=inferred_name,
        source_dir=str(course_dir.resolve()),
        profile=ProfileName.FULL,
        language="zh-TW",
        lectures=lectures,
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

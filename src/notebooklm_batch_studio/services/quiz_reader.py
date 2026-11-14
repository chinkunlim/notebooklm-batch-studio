"""Read a generated quiz (Markdown sheet plus JSON) for the study portal, HTTP and MCP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.models import Course


def _resolve_quiz_dir(courses_output_dir: Path, course: Course, lecture_no: int) -> Path:
    """Resolve the output directory containing quizzes for a lecture or course scope.

    Args:
        courses_output_dir: Root of all course output folders.
        course: Course domain entity.
        lecture_no: Lecture sequence number, or 0 for course-wide quizzes.

    Returns:
        Target directory Path for quiz lookup.
    """
    if lecture_no == 0:
        return courses_output_dir / course.code / "_course_synthesis"
    lec = next((item for item in course.lectures if item.no == lecture_no), None)
    lec_topic = lec.topic if lec else "lecture"
    return courses_output_dir / course.code / f"{lecture_no:02d}_{lec_topic}"


def _find_variant_file(quiz_dir: Path, variant: str, suffix: str, fallback: str) -> Path:
    """Find the first matching quiz variant artifact file inside `quiz_dir`.

    Args:
        quiz_dir: Directory containing quiz outputs.
        variant: Quiz variant identifier or filename prefix.
        suffix: Filename suffix pattern including extension.
        fallback: Fallback relative filename when no prefix variant exists.

    Returns:
        First matching Path if found, else `quiz_dir / fallback`.
    """
    for candidate in (variant, f"quiz_{variant}", variant.replace("quiz_", "")):
        path = quiz_dir / f"{candidate}_{suffix}"
        if path.exists():
            return path
    return quiz_dir / fallback


def read_quiz_content(
    courses_output_dir: Path, course: Course, lecture_no: int, **options: Any
) -> dict[str, Any]:
    """Locate and read one quiz's question or answer sheet and its JSON.

    Args:
        courses_output_dir: Root of all course output folders.
        course: The course.
        lecture_no: Lecture number, or 0 for course-wide quizzes.
        **options: Optional `variant` (default 'quiz_1') and `with_answers` (bool).

    Returns:
        Dictionary with the Markdown sheet and the parsed quiz JSON.

    Raises:
        FileNotFoundError: If the quiz files have not been produced yet.
    """
    variant = str(options.get("variant", "quiz_1"))
    with_answers = bool(options.get("with_answers", False))
    quiz_dir = _resolve_quiz_dir(courses_output_dir, course, lecture_no)
    suffix = "答案卷.md" if with_answers else "題目卷.md"
    md_file = _find_variant_file(quiz_dir, variant, suffix, suffix)
    json_file = _find_variant_file(quiz_dir, variant, "quiz.json", "quiz.json")
    if not md_file.exists():
        raise FileNotFoundError(f"Quiz artifact not found for {course.code} L{lecture_no} ({variant})")

    json_content = json.loads(json_file.read_text(encoding="utf-8")) if json_file.exists() else None
    return {
        "course.code": course.code,
        "lecture_no": lecture_no,
        "variant": variant,
        "with_answers": with_answers,
        "markdown": md_file.read_text(encoding="utf-8"),
        "json_data": json_content,
        "quiz": json_content,
    }

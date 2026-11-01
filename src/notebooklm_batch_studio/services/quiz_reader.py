"""Read a generated quiz (Markdown sheet plus JSON) for the study portal, HTTP and MCP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.models import Course


def read_quiz_content(
    courses_output_dir: Path, course: Course, lecture_no: int, variant: str, with_answers: bool
) -> dict[str, Any]:
    """Locate and read one quiz's question or answer sheet and its JSON.

    Args:
        courses_output_dir: Root of all course output folders.
        course: The course.
        lecture_no: Lecture number, or 0 for course-wide quizzes.
        variant: File prefix such as 'quiz_1', 'quiz_1_v2' or 'course_mock_exam'.
        with_answers: Return the answer sheet instead of the question sheet.

    Returns:
        Dictionary with the Markdown sheet and the parsed quiz JSON.

    Raises:
        FileNotFoundError: If the quiz files have not been produced yet.
    """
    if lecture_no == 0:
        quiz_dir = courses_output_dir / course.code / "_course_synthesis"
    else:
        lec = next((item for item in course.lectures if item.no == lecture_no), None)
        lec_topic = lec.topic if lec else "lecture"
        lec_dir_name = f"{lecture_no:02d}_{lec_topic}"
        quiz_dir = courses_output_dir / course.code / lec_dir_name

    suffix = "答案卷.md" if with_answers else "題目卷.md"
    candidates = [variant, f"quiz_{variant}", variant.replace("quiz_", "")]
    md_file = quiz_dir / suffix
    for c in candidates:
        v_md = quiz_dir / f"{c}_{suffix}"
        if v_md.exists():
            md_file = v_md
            break

    json_file = quiz_dir / "quiz.json"
    for c in candidates:
        v_json = quiz_dir / f"{c}_quiz.json"
        if v_json.exists():
            json_file = v_json
            break

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

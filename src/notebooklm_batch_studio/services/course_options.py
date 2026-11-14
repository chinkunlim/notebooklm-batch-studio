"""Course option schema and per-job option resolution helpers."""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from typing import Any

from notebooklm_batch_studio.domain.models import (
    GENERATION_OPTION_CHOICES,
    NUMBER_OPTION_RANGES,
    TEXT_OPTION_LIMITS,
    ArtifactJob,
    Course,
    GenerationOptions,
    effective_options,
    parse_chapter_range,
)

logger = logging.getLogger(__name__)

# Which options matter for each kind of output (by artifact-type prefix after "course_").
_FIELDS_BY_PREFIX = (
    ("quiz", ["quiz_questions", "quiz_difficulty"]),
    ("mock_exam", ["quiz_difficulty"]),
    ("flashcards", ["flashcards_quantity", "flashcards_difficulty"]),
    ("audio", ["audio_format", "audio_length"]),
    ("infographic", ["infographic_orientation", "infographic_detail", "infographic_style", "device_exports"]),
    ("slide_deck", ["slide_format", "slide_length", "slide_download"]),
    ("video", ["video_format", "video_style", "video_style_prompt"]),
)


def fields_for_type(artifact_type: str) -> list[str]:
    """List the options a given output type uses (every type also takes extra instructions).

    Args:
        artifact_type: Artifact type value.

    Returns:
        Option names relevant to that type.
    """
    value = artifact_type.removeprefix("course_")
    scope = ["chapter_range"] if artifact_type.startswith("course_") else []
    for prefix, fields in _FIELDS_BY_PREFIX:
        if value.startswith(prefix):
            return [*fields, *scope, "extra_instructions"]
    return [*scope, "extra_instructions"]


def option_choices() -> dict[str, Any]:
    """Allowed values for every option: a list, None for on/off, 'text', or a {min, max} range.

    Returns:
        Option name to its allowed values.
    """
    choices: dict[str, Any] = {k: list(v) if v else None for k, v in GENERATION_OPTION_CHOICES.items()}
    choices.update({k: "text" for k in TEXT_OPTION_LIMITS})
    choices["chapter_range"] = "text"
    choices.update({k: {"min": low, "max": high} for k, (low, high) in NUMBER_OPTION_RANGES.items()})
    return choices


def default_options() -> dict[str, Any]:
    """The project defaults a course starts with (what applies when nothing is changed).

    Returns:
        Option name to default value, including the course-level language and mock exam size.
    """
    defaults = dataclasses.asdict(GenerationOptions())
    defaults.update(language="zh-TW", mock_exam_questions=50, exam_date="")
    return defaults


def job_overrides(job: ArtifactJob) -> dict[str, Any]:
    """Read one job's own option overrides (stored as JSON in `style_options`).

    Args:
        job: Artifact job.

    Returns:
        The overrides, or an empty dict when none are set or the stored value is unreadable.
    """
    if not job.style_options:
        return {}
    try:
        data = json.loads(job.style_options)
    except ValueError:
        logger.warning("Ignoring unreadable style_options on job %s", job.id)
        return {}
    return data if isinstance(data, dict) else {}


def apply_job_settings(job: ArtifactJob, course: Course) -> tuple[ArtifactJob, Course]:
    """Resolve the settings one job runs with: course options, its own overrides, extra instructions.

    Args:
        job: Job about to run.
        course: Its course.

    Returns:
        The job with extra instructions appended to its prompt, and the course carrying the
        effective options for this job (SPEC-006).
    """
    try:
        options = effective_options(course.generation_options, job_overrides(job))
    except ValueError as err:
        logger.warning("Ignoring invalid overrides on job %s: %s", job.id, err)
        options = course.generation_options
    prompt = job.custom_prompt or ""
    # The question count in the prompt follows the settings (quiz: quiz_questions, mock exam:
    # the course's mock_exam_questions), so changing a count changes what Gemini Notebook is asked.
    value = job.artifact_type.value.removeprefix("course_")
    if value.startswith("quiz"):
        count = course.mock_exam_questions if job.lecture_no is None else options.quiz_questions
        prompt = re.sub(r"生成 \d+ 題", f"生成 {count} 題", prompt)
    elif value.startswith("mock_exam"):
        prompt = re.sub(r"生成 \d+ 題", f"生成 {course.mock_exam_questions} 題", prompt)
    lectures = course.lectures
    wanted = parse_chapter_range(options.chapter_range) if options.chapter_range else None
    if job.lecture_no is None and wanted:
        # A course-wide output limited to some chapters (e.g. a midterm on Ch01-Ch03) uses only
        # those sources, and its Gemini Notebook title prefix shows that range.
        lectures = [lec for lec in course.lectures if lec.no in wanted] or course.lectures
        prompt = f"{prompt}\n\n範圍：只涵蓋第 {options.chapter_range} 講的內容。".strip()
    if options.extra_instructions:
        prompt = f"{prompt}\n\n補充要求：{options.extra_instructions}".strip()
    return (
        dataclasses.replace(job, custom_prompt=prompt or None),
        dataclasses.replace(course, generation_options=options, lectures=lectures),
    )

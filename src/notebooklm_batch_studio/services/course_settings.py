"""Per-course settings and versioned regeneration, kept apart from the orchestrator.

Generation options change how future NotebookLM generations look (infographic orientation,
audio format, ...). Regeneration enqueues a new version of one artifact slot and never deletes
or overwrites the older version (ADR-005).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import uuid
from typing import Any

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import (
    GENERATION_OPTION_CHOICES,
    NUMBER_OPTION_RANGES,
    TEXT_OPTION_LIMITS,
    ArtifactJob,
    ArtifactType,
    Course,
    GenerationOptions,
    JobStatus,
    effective_options,
    merge_generation_options,
)
from notebooklm_batch_studio.domain.naming import label_for
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol, QueueRepositoryProtocol
from notebooklm_batch_studio.services.prompt_generator import PromptGenerator
from notebooklm_batch_studio.services.worker_pool import generate_jobs_for_course

CHAPTER_TYPES = [t.value for t in ArtifactType if not t.value.startswith("course_")]
COURSE_TYPES = [t.value for t in ArtifactType if t.value.startswith("course_")]
UNSTARTED = [JobStatus.PENDING, JobStatus.QUOTA_WAIT, JobStatus.FAILED]
LANGUAGES = ("zh-TW", "en", "bilingual")
MOCK_EXAM_RANGE = (10, 100)

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
    for prefix, fields in _FIELDS_BY_PREFIX:
        if value.startswith(prefix):
            return [*fields, "extra_instructions"]
    return ["extra_instructions"]


def option_choices() -> dict[str, Any]:
    """Allowed values for every option: a list, None for on/off, "text", or a {min, max} range.

    Returns:
        Option name to its allowed values.
    """
    choices: dict[str, Any] = {k: list(v) if v else None for k, v in GENERATION_OPTION_CHOICES.items()}
    choices.update({k: "text" for k in TEXT_OPTION_LIMITS})
    choices.update({k: {"min": low, "max": high} for k, (low, high) in NUMBER_OPTION_RANGES.items()})
    return choices


def default_options() -> dict[str, Any]:
    """The project defaults a course starts with (what applies when nothing is changed).

    Returns:
        Option name to default value, including the course-level language and mock exam size.
    """
    defaults = dataclasses.asdict(GenerationOptions())
    defaults.update(language="zh-TW", mock_exam_questions=50)
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
    # the course's mock_exam_questions), so changing a count changes what NotebookLM is asked.
    value = job.artifact_type.value.removeprefix("course_")
    if value.startswith("quiz"):
        count = course.mock_exam_questions if job.lecture_no is None else options.quiz_questions
        prompt = re.sub(r"生成 \d+ 題", f"生成 {count} 題", prompt)
    elif value.startswith("mock_exam"):
        prompt = re.sub(r"生成 \d+ 題", f"生成 {course.mock_exam_questions} 題", prompt)
    if options.extra_instructions:
        prompt = f"{prompt}\n\n補充要求：{options.extra_instructions}".strip()
    return (
        dataclasses.replace(job, custom_prompt=prompt or None),
        dataclasses.replace(course, generation_options=options),
    )


logger = logging.getLogger(__name__)


class CourseSettingsService:
    """Read and change generation options; enqueue new versions of artifacts."""

    def __init__(self, course_repo: CourseRepositoryProtocol, queue_repo: QueueRepositoryProtocol) -> None:
        """Bind the service to its repositories.

        Args:
            course_repo: Course persistence.
            queue_repo: Job queue persistence.
        """
        self.course_repo = course_repo
        self.queue_repo = queue_repo

    def _course(self, code: str) -> Course:
        """Load a course or raise.

        Args:
            code: Course code.

        Returns:
            The course.

        Raises:
            CourseNotFoundError: When the course does not exist.
        """
        course = self.course_repo.get_course(code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {code}")
        return course

    def get_options(self, code: str) -> dict[str, Any]:
        """Return a course's generation options and the allowed values.

        Args:
            code: Course code.

        Returns:
            Dictionary with `options` (current values) and `choices` (allowed values; None = boolean).
        """
        course = self._course(code)
        options = dataclasses.asdict(course.generation_options)
        options.update(language=course.language, mock_exam_questions=course.mock_exam_questions)
        choices = option_choices()
        choices.update(
            language=list(LANGUAGES),
            mock_exam_questions={"min": MOCK_EXAM_RANGE[0], "max": MOCK_EXAM_RANGE[1]},
        )
        return {"options": options, "choices": choices, "defaults": default_options()}

    def set_options(self, code: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Validate and store option changes; they apply to generations started afterwards.

        Args:
            code: Course code.
            changes: Option name to new value.

        Returns:
            The updated options in the same shape as `get_options`.

        Raises:
            ValueError: On an unknown option or a disallowed value.
        """
        course = self._course(code)
        changes = dict(changes)
        language = changes.pop("language", course.language)
        mock = changes.pop("mock_exam_questions", course.mock_exam_questions)
        if language not in LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(LANGUAGES)}")
        if (
            not isinstance(mock, int)
            or isinstance(mock, bool)
            or not MOCK_EXAM_RANGE[0] <= mock <= MOCK_EXAM_RANGE[1]
        ):
            raise ValueError(
                "mock_exam_questions must be a whole number from "
                f"{MOCK_EXAM_RANGE[0]} to {MOCK_EXAM_RANGE[1]}"
            )
        updated = merge_generation_options(course.generation_options, changes)
        self.course_repo.update_generation_options(code, updated)
        if (language, mock) != (course.language, course.mock_exam_questions):
            self.course_repo.update_course_basics(code, language, mock)
        logger.info("Updated generation options for %s: %s", code, sorted(changes))
        return self.get_options(code)

    def regenerate(self, code: str, lecture_no: int | None, artifact_type: str) -> dict[str, Any]:
        """Enqueue the next version of one artifact slot, keeping every older version.

        Args:
            code: Course code.
            lecture_no: Lecture number, or None for a course-wide artifact.
            artifact_type: Artifact type value (e.g. 'infographic').

        Returns:
            Summary of the new job (id, version, label).

        Raises:
            ValueError: When the artifact type is unknown or the lecture does not exist.
        """
        course = self._course(code)
        art_type = ArtifactType(artifact_type)
        lecture = next((lec for lec in course.lectures if lec.no == lecture_no), None)
        if lecture_no is not None and lecture is None:
            raise ValueError(f"Lecture {lecture_no} not found in course {code}")

        version = self.queue_repo.max_version(code, lecture_no, art_type) + 1
        slot = [
            j
            for j in self.queue_repo.list_jobs(course_code=code)
            if j.lecture_no == lecture_no and j.artifact_type == art_type
        ]
        latest = max(slot, key=lambda j: j.version) if slot else None
        # Always start from the current blueprint: an older version's stored prompt may predate
        # prompt fixes (e.g. the 10-question quizzes, ISSUE-017). Edit the queued job to customize.
        topic = lecture.topic if lecture else f"{course.code} 全範圍整合"
        prompt = PromptGenerator().get_base_blueprint_prompt(art_type, topic, course.name, course.language)
        job = ArtifactJob(
            id=str(uuid.uuid4()),
            course_code=code,
            lecture_no=lecture_no,
            artifact_type=art_type,
            custom_prompt=prompt,
            version=version,
            # The output's own settings carry over to the new version (SPEC-006).
            style_options=latest.style_options if latest else None,
        )
        self.queue_repo.enqueue_jobs([job])
        logger.info("Enqueued %s v%d for %s L%s", art_type.value, version, code, lecture_no)
        return {"job_id": job.id, "version": version, "label": label_for(art_type), "lecture_no": lecture_no}

    def get_artifact_selection(self, code: str) -> dict[str, Any]:
        """Return which artifact types a course generates, with labels for every choice.

        Args:
            code: Course code.

        Returns:
            Dictionary with `chapter` and `course` (selected type values) and `choices`
            (type value and label for each scope).
        """
        course = self._course(code)
        types = {j.artifact_type.value for j in generate_jobs_for_course(course)}
        if course.selected_chapter_artifacts or course.selected_course_artifacts:
            types = set(course.selected_chapter_artifacts) | set(course.selected_course_artifacts)
        return {
            "chapter": [t for t in CHAPTER_TYPES if t in types],
            "course": [t for t in COURSE_TYPES if t in types],
            "choices": {
                "chapter": [{"value": t, "label": label_for(t)} for t in CHAPTER_TYPES],
                "course": [{"value": t, "label": label_for(t)} for t in COURSE_TYPES],
            },
        }

    def set_artifact_selection(self, code: str, chapter: list[str], whole: list[str]) -> dict[str, Any]:
        """Change which artifact types a course generates after it was added.

        Newly chosen types are queued (skipped jobs of that type are revived); unchosen types have
        their unstarted jobs skipped. Finished outputs are never deleted.

        Args:
            code: Course code.
            chapter: Per-lecture artifact type values to generate.
            whole: Course-wide artifact type values to generate.

        Returns:
            Counts of queued, revived and skipped jobs plus the new selection.

        Raises:
            ValueError: When a value is not a known type of the right scope.
        """
        bad = [t for t in chapter if t not in CHAPTER_TYPES] + [t for t in whole if t not in COURSE_TYPES]
        if bad:
            raise ValueError(f"Unknown or wrong-scope artifact types: {', '.join(bad)}")
        before = self.get_artifact_selection(code)
        old = set(before["chapter"]) | set(before["course"])
        new = set(chapter) | set(whole)
        self.course_repo.update_artifact_selection(code, list(chapter), list(whole))
        removed, added = sorted(old - new), sorted(new - old)
        skipped = self.queue_repo.set_types_status(code, removed, UNSTARTED, JobStatus.SKIPPED)
        revived = self.queue_repo.set_types_status(code, added, [JobStatus.SKIPPED], JobStatus.PENDING)
        course = self._course(code)
        queued = self.queue_repo.enqueue_jobs(
            [j for j in generate_jobs_for_course(course) if j.artifact_type.value in added]
        )
        logger.info("Artifact selection for %s: +%s -%s", code, added, removed)
        return {"queued": queued, "revived": revived, "skipped": skipped, **self.get_artifact_selection(code)}

    def _job(self, job_id: str) -> ArtifactJob:
        """Load a job or raise.

        Args:
            job_id: Job id.

        Returns:
            The job.

        Raises:
            ValueError: When the job does not exist.
        """
        job = self.queue_repo.get_job(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        return job

    def get_job_options(self, job_id: str) -> dict[str, Any]:
        """Return one output's own settings, the settings it will actually use, and its fields.

        Args:
            job_id: Job id.

        Returns:
            Dictionary with `overrides`, `effective` (course + overrides), `fields` relevant to the
            type, `choices`, `status`, and `unsupported` notes for options the library lacks.
        """
        job = self._job(job_id)
        course = self._course(job.course_code)
        overrides = job_overrides(job)
        effective = effective_options(course.generation_options, overrides)
        is_quiz = job.artifact_type.value.removeprefix("course_").startswith(("quiz", "mock_exam"))
        return {
            "job_id": job.id,
            "artifact_type": job.artifact_type.value,
            "label": label_for(job.artifact_type),
            "status": job.status.value,
            "overrides": overrides,
            "effective": dataclasses.asdict(effective),
            "fields": fields_for_type(job.artifact_type.value),
            "choices": option_choices(),
            "defaults": default_options(),
            "unsupported": ["題型（選擇題／簡答題）：等 notebooklm-py 下一版支援後開放"] if is_quiz else [],
        }

    def set_job_options(self, job_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
        """Replace one output's own settings; empty values fall back to the course settings.

        Args:
            job_id: Job id.
            overrides: Option name to value; "" or None removes that override.

        Returns:
            The same shape as `get_job_options`.

        Raises:
            ValueError: On an option the type does not use, or an invalid value.
        """
        job = self._job(job_id)
        allowed = set(fields_for_type(job.artifact_type.value))
        cleaned = {k: v for k, v in overrides.items() if v not in ("", None)}
        bad = sorted(set(cleaned) - allowed)
        if bad:
            raise ValueError(f"Options not used by {job.artifact_type.value}: {', '.join(bad)}")
        merge_generation_options(self._course(job.course_code).generation_options, cleaned)  # validates
        self.queue_repo.update_job_style_options(
            job_id, json.dumps(cleaned, ensure_ascii=False) if cleaned else None
        )
        logger.info("Updated own settings of job %s: %s", job_id, sorted(cleaned))
        return self.get_job_options(job_id)

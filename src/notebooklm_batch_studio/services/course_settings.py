"""Per-course settings and versioned regeneration, kept apart from the orchestrator.

Generation options change how future NotebookLM generations look (infographic orientation,
audio format, ...). Regeneration enqueues a new version of one artifact slot and never deletes
or overwrites the older version (ADR-005).
"""

from __future__ import annotations

import dataclasses
import logging
import uuid
from typing import Any

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import (
    GENERATION_OPTION_CHOICES,
    ArtifactJob,
    ArtifactType,
    Course,
    JobStatus,
    merge_generation_options,
)
from notebooklm_batch_studio.domain.naming import label_for
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol, QueueRepositoryProtocol
from notebooklm_batch_studio.services.prompt_generator import PromptGenerator
from notebooklm_batch_studio.services.worker_pool import generate_jobs_for_course

CHAPTER_TYPES = [t.value for t in ArtifactType if not t.value.startswith("course_")]
COURSE_TYPES = [t.value for t in ArtifactType if t.value.startswith("course_")]
UNSTARTED = [JobStatus.PENDING, JobStatus.QUOTA_WAIT, JobStatus.FAILED]

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
        return {
            "options": dataclasses.asdict(course.generation_options),
            "choices": {k: list(v) if v else None for k, v in GENERATION_OPTION_CHOICES.items()},
        }

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
        updated = merge_generation_options(course.generation_options, changes)
        self.course_repo.update_generation_options(code, updated)
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
        previous = [
            j
            for j in self.queue_repo.list_jobs(course_code=code)
            if j.lecture_no == lecture_no and j.artifact_type == art_type
        ]
        prompt = max(previous, key=lambda j: j.version).custom_prompt if previous else None
        if prompt is None:
            topic = lecture.topic if lecture else f"{course.code} 全範圍整合"
            prompt = PromptGenerator().get_base_blueprint_prompt(
                art_type, topic, course.name, course.language
            )
        job = ArtifactJob(
            id=str(uuid.uuid4()),
            course_code=code,
            lecture_no=lecture_no,
            artifact_type=art_type,
            custom_prompt=prompt,
            version=version,
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

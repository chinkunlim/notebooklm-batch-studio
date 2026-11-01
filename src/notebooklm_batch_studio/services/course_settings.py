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
    merge_generation_options,
)
from notebooklm_batch_studio.domain.naming import label_for
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol, QueueRepositoryProtocol
from notebooklm_batch_studio.services.prompt_generator import PromptGenerator

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

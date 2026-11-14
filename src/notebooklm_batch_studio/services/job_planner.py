"""Course job matrix planning: builds scheduled ArtifactJob records from profiles or selections."""

from __future__ import annotations

import logging
import uuid

from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    JobStatus,
    ProfileName,
)
from notebooklm_batch_studio.services.prompt_generator import PromptGenerator

logger = logging.getLogger(__name__)

_PROFILE_ARTIFACT_TYPES: dict[ProfileName, list[ArtifactType]] = {
    ProfileName.FULL: [
        ArtifactType.AUDIO,
        ArtifactType.QUIZ_1,
        ArtifactType.QUIZ_2,
        ArtifactType.QUIZ_3,
        ArtifactType.INFOGRAPHIC,
        ArtifactType.MIND_MAP,
        ArtifactType.FLASHCARDS,
        ArtifactType.STUDY_GUIDE,
    ],
    ProfileName.QUIZ_ONLY: [
        ArtifactType.QUIZ_1,
        ArtifactType.QUIZ_2,
        ArtifactType.QUIZ_3,
        ArtifactType.FLASHCARDS,
    ],
    ProfileName.EXAM_PREP: [
        ArtifactType.QUIZ_3,
        ArtifactType.STUDY_GUIDE,
    ],
}


def _get_types_for_profile(profile: ProfileName) -> list[ArtifactType]:
    """Return the list of artifact types required for a single lecture under the given profile.

    Args:
        profile: Selected generation profile.

    Returns:
        List of ArtifactType enum values.
    """
    return list(_PROFILE_ARTIFACT_TYPES.get(profile, ()))


def _make_job(
    course_code: str,
    lecture_no: int | None,
    art_type: ArtifactType,
    custom_prompt: str | None = None,
) -> ArtifactJob:
    """Create a new pending ArtifactJob with a fresh UUID.

    Args:
        course_code: Course code.
        lecture_no: Sequence number or None for course-level.
        art_type: Artifact type.
        custom_prompt: Optional tailored prompt.

    Returns:
        ArtifactJob domain object.
    """
    return ArtifactJob(
        id=str(uuid.uuid4()),
        course_code=course_code,
        lecture_no=lecture_no,
        artifact_type=art_type,
        status=JobStatus.PENDING,
        custom_prompt=custom_prompt,
    )


def _parse_artifact_names(names: list[str], label: str) -> list[ArtifactType]:
    """Parse configured artifact type names, logging and skipping unknown entries.

    Args:
        names: Artifact type string values.
        label: Scope label used in warning logs (e.g. 'chapter' or 'course').

    Returns:
        Validated ArtifactType list preserving order.
    """
    parsed: list[ArtifactType] = []
    for name in names:
        try:
            parsed.append(ArtifactType(name))
        except ValueError:
            logger.warning("Unknown %s artifact type: %s", label, name)
    return parsed


def _generate_granular_jobs(course: Course, prompt_gen: PromptGenerator) -> list[ArtifactJob]:
    """Generate jobs from explicit per-chapter and course-wide artifact selections.

    Args:
        course: Course domain entity with custom artifact selections.
        prompt_gen: Prompt blueprint generator.

    Returns:
        Ordered list of ArtifactJob objects.
    """
    chapter_types = _parse_artifact_names(course.selected_chapter_artifacts, "chapter")
    course_types = _parse_artifact_names(course.selected_course_artifacts, "course")
    jobs: list[ArtifactJob] = []
    for lec in course.lectures:
        for art_type in chapter_types:
            p = prompt_gen.get_base_blueprint_prompt(art_type, lec.topic, course.name, course.language)
            jobs.append(_make_job(course.code, lec.no, art_type, custom_prompt=p))

    course_scope = f"{course.code} 全範圍整合"
    for course_art in course_types:
        p = prompt_gen.get_base_blueprint_prompt(course_art, course_scope, course.name, course.language)
        jobs.append(_make_job(course.code, None, course_art, custom_prompt=p))

    logger.info(
        "Generated %d granular jobs for course %s (chapter_types=%d, course_types=%d)",
        len(jobs),
        course.code,
        len(chapter_types),
        len(course_types),
    )
    return jobs


def _generate_profile_jobs(course: Course, prompt_gen: PromptGenerator) -> list[ArtifactJob]:
    """Generate jobs using the course's legacy predefined generation profile.

    Args:
        course: Course domain entity using a preset profile.
        prompt_gen: Prompt blueprint generator.

    Returns:
        Ordered list of ArtifactJob objects.
    """
    jobs: list[ArtifactJob] = []
    types_for_lecture = _get_types_for_profile(course.profile)
    for lec in course.lectures:
        for art_type in types_for_lecture:
            p = prompt_gen.get_base_blueprint_prompt(art_type, lec.topic, course.name, course.language)
            jobs.append(_make_job(course.code, lec.no, art_type, custom_prompt=p))

    if course.profile in (ProfileName.FULL, ProfileName.EXAM_PREP):
        for course_art in (ArtifactType.COURSE_MOCK_EXAM, ArtifactType.COURSE_MIND_MAP):
            p = prompt_gen.get_base_blueprint_prompt(
                course_art, f"{course.code} 全範圍整合", course.name, course.language
            )
            jobs.append(_make_job(course.code, None, course_art, custom_prompt=p))

    logger.info("Generated %d jobs for course %s (profile=%s)", len(jobs), course.code, course.profile.value)
    return jobs


def generate_jobs_for_course(course: Course) -> list[ArtifactJob]:
    """Create the matrix of scheduled ArtifactJob entities for a course based on settings.

    Supports custom granular selections (selected_chapter_artifacts, selected_course_artifacts)
    or falls back to legacy predefined profiles.

    Args:
        course: The Course domain entity containing lectures and selected settings.

    Returns:
        List of ready-to-enqueue ArtifactJob objects with unique identifiers.
    """
    prompt_gen = PromptGenerator()
    if course.selected_chapter_artifacts or course.selected_course_artifacts:
        return _generate_granular_jobs(course, prompt_gen)
    return _generate_profile_jobs(course, prompt_gen)

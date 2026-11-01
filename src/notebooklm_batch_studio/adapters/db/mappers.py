"""Convert ORM records into immutable domain objects (split out of `repository.py`)."""

from __future__ import annotations

import json

from notebooklm_batch_studio.adapters.db.models import ArtifactJobRecord, CourseRecord, LectureRecord
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    GenerationOptions,
    JobStatus,
    Lecture,
    ProfileName,
    merge_generation_options,
)


def options_from_json(raw: str | None) -> GenerationOptions:
    """Decode stored generation options, ignoring unknown or invalid keys.

    Args:
        raw: JSON text from the courses table, or None.

    Returns:
        GenerationOptions (defaults for anything missing).
    """
    if not raw:
        return GenerationOptions()
    options = GenerationOptions()
    for key, value in json.loads(raw).items():
        try:
            options = merge_generation_options(options, {key: value})
        except ValueError:
            continue
    return options


def to_domain_lecture(record: LectureRecord) -> Lecture:
    """Convert a LectureRecord ORM instance to a pure domain Lecture object.

    Args:
        record: Database lecture record.

    Returns:
        Immutable domain Lecture entity.
    """
    return Lecture(
        no=record.no,
        topic=record.topic,
        filename=record.filename,
        sha256=record.sha256,
        source_id=record.source_id,
        upload_status=getattr(record, "upload_status", "pending") or "pending",
        error_message=getattr(record, "error_message", None),
    )


def to_domain_course(record: CourseRecord, lectures: list[Lecture]) -> Course:
    """Convert a CourseRecord ORM instance to a pure domain Course object.

    Args:
        record: Database course record.
        lectures: Associated domain lecture objects.

    Returns:
        Immutable domain Course entity.
    """
    return Course(
        code=record.code,
        name=record.name,
        source_dir=record.source_dir,
        notebook_id=record.notebook_id,
        profile=(
            ProfileName(record.profile)
            if record.profile in ProfileName._value2member_map_
            else ProfileName.FULL
        ),
        language=record.language,
        exam_date=record.exam_date,
        watch=record.watch,
        mock_exam_questions=record.mock_exam_questions,
        lectures=lectures,
        generation_options=options_from_json(getattr(record, "generation_options", None)),
        selected_chapter_artifacts=json.loads(record.selected_chapter_artifacts or "[]"),
        selected_course_artifacts=json.loads(record.selected_course_artifacts or "[]"),
        paused=bool(getattr(record, "paused", False)),
        reuse_notebook=bool(getattr(record, "reuse_notebook", True)),
    )


def to_domain_job(record: ArtifactJobRecord) -> ArtifactJob:
    """Convert an ArtifactJobRecord ORM instance to a pure domain ArtifactJob object.

    Args:
        record: Database job record.

    Returns:
        Immutable domain ArtifactJob entity.
    """
    return ArtifactJob(
        id=record.id,
        course_code=record.course_code,
        lecture_no=record.lecture_no,
        artifact_type=ArtifactType(record.artifact_type),
        status=JobStatus(record.status),
        attempts=record.attempts,
        worker_id=record.worker_id,
        error_message=record.error_message,
        output_file=record.output_file,
        custom_prompt=getattr(record, "custom_prompt", None),
        style_options=getattr(record, "style_options", None),
        interactive_path=getattr(record, "interactive_path", None),
        source_origin=getattr(record, "source_origin", "auto"),
        quota_blocked_at=record.quota_blocked_at,
        cooldown_until=record.cooldown_until,
        created_at=record.created_at,
        updated_at=record.updated_at,
        version=getattr(record, "version", 1) or 1,
        artifact_ids=tuple(json.loads(record.artifact_ids)) if record.artifact_ids else (),
    )

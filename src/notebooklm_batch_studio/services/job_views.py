"""Presentation helpers for the orchestrator: job rows for API/MCP and preview job lists.

Kept apart from `orchestrator.py` so the service class stays focused on workflow steps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course, Lecture
from notebooklm_batch_studio.domain.naming import label_for
from notebooklm_batch_studio.services.job_planner import generate_jobs_for_course

# Download-route prefix for quarantined files under DATA_DIR/needs_review/. Refs: ISSUE-010
NEEDS_REVIEW_PREFIX = "_needs_review"


def _relative_output_path(
    output_file: str | None, course_dir: Path, needs_review_dir: Path | None
) -> str | None:
    """Compute display-relative artifact path across course output and quarantine folders.

    Args:
        output_file: Stored absolute or relative artifact path.
        course_dir: Course output directory.
        needs_review_dir: Optional quarantine root directory.

    Returns:
        Relative URL path segment or None when no output file exists.
    """
    if not output_file:
        return None
    try:
        p = Path(output_file)
        if p.is_relative_to(course_dir):
            return str(p.relative_to(course_dir))
        if needs_review_dir is not None and p.is_relative_to(needs_review_dir):
            return f"{NEEDS_REVIEW_PREFIX}/{p.relative_to(needs_review_dir)}"
        return p.name
    except Exception:
        return Path(output_file).name


def _format_job_row(j: ArtifactJob, rel_path: str | None) -> dict[str, Any]:
    """Serialize one ArtifactJob entity into an API/MCP response dictionary.

    Args:
        j: Domain ArtifactJob instance.
        rel_path: Relative file path computed by `_relative_output_path`.

    Returns:
        JSON-serializable job summary dictionary.
    """
    return {
        "id": j.id,
        "lecture_no": j.lecture_no,
        "artifact_type": j.artifact_type.value,
        "label": label_for(j.artifact_type),
        "version": j.version,
        "style_options": j.style_options,
        "artifact_ids": list(j.artifact_ids),
        "cooldown_until": j.cooldown_until.isoformat() if j.cooldown_until else None,
        "status": j.status.value,
        "custom_prompt": j.custom_prompt,
        "output_file": j.output_file,
        "rel_path": rel_path,
        "error_message": j.error_message,
        "attempts": j.attempts,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "updated_at": j.updated_at.isoformat() if j.updated_at else None,
    }


def format_jobs_data(
    jobs: list[ArtifactJob], course_dir: Path, needs_review_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Format artifact jobs for API representation including relative paths.

    Args:
        jobs: List of ArtifactJob entities.
        course_dir: Base directory of the course output.
        needs_review_dir: Quarantine directory; its files get a `_needs_review/...` rel_path.

    Returns:
        List of formatted job dictionaries.
    """
    return [
        _format_job_row(j, _relative_output_path(j.output_file, course_dir, needs_review_dir)) for j in jobs
    ]


def preview_job_types(
    course: Course, chapter_artifacts: list[str] | None, course_artifacts: list[str] | None
) -> list[ArtifactType]:
    """List the artifact type of every job a course would get.

    Args:
        course: Scanned (unsaved) course.
        chapter_artifacts: Custom per-lecture artifact type values, or None for the profile.
        course_artifacts: Custom course-wide artifact type values, or None for the profile.

    Returns:
        One artifact type per job.
    """
    if chapter_artifacts is None and course_artifacts is None:
        return [job.artifact_type for job in generate_jobs_for_course(course)]
    known = {t.value for t in ArtifactType}
    chapter = [ArtifactType(v) for v in chapter_artifacts or [] if v in known]
    whole = [ArtifactType(v) for v in course_artifacts or [] if v in known]
    return chapter * len(course.lectures) + whole


def lecture_to_dict(lec: Lecture) -> dict[str, Any]:
    """Serialize a domain Lecture entity for detail responses.

    Args:
        lec: Lecture domain object.

    Returns:
        Dictionary of lecture metadata and upload state.
    """
    return {
        "no": lec.no,
        "topic": lec.topic,
        "filename": lec.filename,
        "source_id": lec.source_id,
        "pdf_hash": lec.sha256,
        "upload_status": lec.upload_status,
        "error_message": lec.error_message,
    }

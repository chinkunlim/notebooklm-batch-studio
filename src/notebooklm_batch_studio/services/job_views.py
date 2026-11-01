"""Presentation helpers for the orchestrator: job rows for API/MCP and preview job lists.

Kept apart from `orchestrator.py` so the service class stays focused on workflow steps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course
from notebooklm_batch_studio.services.worker_pool import generate_jobs_for_course

# Download-route prefix for quarantined files under DATA_DIR/needs_review/. Refs: ISSUE-010
NEEDS_REVIEW_PREFIX = "_needs_review"


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
    jobs_data = []
    for j in jobs:
        rel_path = None
        if j.output_file:
            try:
                p = Path(j.output_file)
                if p.is_relative_to(course_dir):
                    rel_path = str(p.relative_to(course_dir))
                elif needs_review_dir is not None and p.is_relative_to(needs_review_dir):
                    rel_path = f"{NEEDS_REVIEW_PREFIX}/{p.relative_to(needs_review_dir)}"
                else:
                    rel_path = p.name
            except Exception:
                rel_path = Path(j.output_file).name
        jobs_data.append(
            {
                "id": j.id,
                "lecture_no": j.lecture_no,
                "artifact_type": j.artifact_type.value,
                "status": j.status.value,
                "custom_prompt": j.custom_prompt,
                "output_file": j.output_file,
                "rel_path": rel_path,
                "error_message": j.error_message,
                "attempts": j.attempts,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            }
        )
    return jobs_data


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

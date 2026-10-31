"""Remote synchronization service: syncs manually generated artifacts from NotebookLM to local storage.

Queries all remote artifacts in a course's linked NotebookLM notebook, identifies artifacts
created on the web interface, downloads them to their corresponding lecture folders or
the manual_artifacts folder, and registers them in the local database.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, JobStatus
from notebooklm_batch_studio.domain.repositories import (
    CourseRepositoryProtocol,
    NotebookLMClientProtocol,
    QueueRepositoryProtocol,
)

logger = logging.getLogger(__name__)


def infer_lecture_no_from_title(title: str, total_lectures: int) -> int | None:
    """Infer the lecture sequence number from artifact title.

    Args:
        title: Artifact title string (e.g. '[Ch02] Quiz' or 'Lecture 3 Mind Map').
        total_lectures: Total number of lectures in the course.

    Returns:
        Inferred lecture sequence number, or None if course-wide or unknown.
    """
    clean = title.strip()
    # Match patterns like [Ch01], [L02], Ch03, Lecture 4
    match = re.search(r"(?:\[?(?:ch|chapter|lecture|l)\s*(\d+)\]?)", clean, re.IGNORECASE)
    if match:
        try:
            num = int(match.group(1))
            if 1 <= num <= total_lectures + 5:
                return num
        except ValueError:
            pass
    return None


def map_remote_kind_to_artifact_type(kind: str) -> ArtifactType:
    """Map NotebookLM artifact kind string to local domain ArtifactType.

    Args:
        kind: Remote artifact kind string (e.g. 'quiz', 'audio', 'flashcards').

    Returns:
        Domain ArtifactType enum.
    """
    k = kind.lower()
    if "flashcard" in k:
        return ArtifactType.FLASHCARDS
    if "mind" in k:
        return ArtifactType.MIND_MAP
    if "audio" in k:
        return ArtifactType.AUDIO
    if "slide" in k:
        return ArtifactType.SLIDE_DECK
    if "infographic" in k:
        return ArtifactType.INFOGRAPHIC
    if "table" in k:
        return ArtifactType.DATA_TABLE
    if "video" in k:
        return ArtifactType.VIDEO
    if "briefing" in k:
        return ArtifactType.REPORTS_BRIEFING
    if "study_guide" in k:
        return ArtifactType.REPORTS_STUDY_GUIDE
    if "blog" in k:
        return ArtifactType.REPORTS_BLOG_POST
    return ArtifactType.QUIZ_ACADEMIC


class RemoteSyncService:
    """Synchronizes remote NotebookLM artifacts back into local repository and disk."""

    def __init__(
        self,
        notebooklm_client: NotebookLMClientProtocol,
        course_repo: CourseRepositoryProtocol,
        queue_repo: QueueRepositoryProtocol,
        output_base_dir: Path,
    ) -> None:
        """Initialize remote synchronization service.

        Args:
            notebooklm_client: Adapter client for NotebookLM communication.
            course_repo: Course repository.
            queue_repo: Job queue repository.
            output_base_dir: Base directory for storing course outputs.
        """
        self.client = notebooklm_client
        self.course_repo = course_repo
        self.queue_repo = queue_repo
        self.output_base_dir = output_base_dir

    async def sync_course(self, course_code: str) -> dict[str, Any]:
        """Fetch remote artifacts for a course and sync new ones locally.

        Args:
            course_code: Course identifier.

        Returns:
            Dictionary summary of synchronized items and count.
        """
        course = self.course_repo.get_course(course_code)
        if not course:
            raise ValueError(f"Course not found: {course_code}")
        if not course.notebook_id:
            raise ValueError(f"Course {course_code} has no linked NotebookLM notebook")

        nb_id = course.notebook_id
        logger.info("Syncing remote artifacts for course %s (notebook: %s)", course_code, nb_id)
        remote_artifacts = await self.client.list_artifacts(nb_id)

        synced_items: list[dict[str, Any]] = []
        course_out = self.output_base_dir / "courses" / course_code

        for art in remote_artifacts:
            art_id = art["id"]
            title = art["title"]
            kind = art["kind"]

            # Infer lecture number
            lec_no = infer_lecture_no_from_title(title, len(course.lectures))
            art_type = map_remote_kind_to_artifact_type(kind)

            if lec_no:
                dest_dir = course_out / f"lecture_{lec_no:02d}"
            else:
                dest_dir = course_out / "manual_artifacts"
            dest_dir.mkdir(parents=True, exist_ok=True)

            safe_title = re.sub(r"[^\w\s\-\[\]]", "_", title).strip() or art_id
            output_file = dest_dir / f"{safe_title}.bin"

            # Check if this artifact is already downloaded
            if output_file.exists():
                continue

            try:
                downloaded_path = await self.client.download_artifact_by_kind(
                    notebook_id=nb_id,
                    artifact_id=art_id,
                    kind=kind,
                    output_path=str(output_file),
                )

                job = ArtifactJob(
                    id=str(uuid.uuid4()),
                    course_code=course_code,
                    lecture_no=lec_no,
                    artifact_type=art_type,
                    status=JobStatus.DONE,
                    output_file=downloaded_path,
                    source_origin="remote_sync",
                    custom_prompt=f"Synced from NotebookLM: {title}",
                )
                self.queue_repo.enqueue_jobs([job])
                synced_items.append({"id": art_id, "title": title, "path": downloaded_path})
                logger.info("Synced remote artifact '%s' to %s", title, downloaded_path)
            except Exception as err:
                logger.warning("Failed to sync remote artifact %s (%s): %s", art_id, title, err)

        return {
            "course_code": course_code,
            "synced_count": len(synced_items),
            "items": synced_items,
        }

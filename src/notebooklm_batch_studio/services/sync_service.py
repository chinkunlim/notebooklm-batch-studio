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


def get_extension_for_kind(kind: str) -> str:
    """Determine file extension based on NotebookLM artifact kind.

    Args:
        kind: Artifact kind string.

    Returns:
        Appropriate file extension with leading dot.
    """
    k = kind.lower()
    if "audio" in k:
        return ".mp3"
    if "video" in k:
        return ".mp4"
    if "slide" in k or "infographic" in k:
        return ".pdf"
    if "report" in k or "briefing" in k or "study_guide" in k or "blog" in k:
        return ".html"
    return ".json"


def extract_synced_art_ids(jobs: list[ArtifactJob]) -> set[str]:
    """Extract set of already synchronized remote artifact IDs from jobs.

    Args:
        jobs: List of ArtifactJob entities.

    Returns:
        Set of remote artifact ID strings.
    """
    ids: set[str] = set()
    for j in jobs:
        if j.source_origin == "remote_sync" and j.custom_prompt and "[" in j.custom_prompt:
            try:
                aid = j.custom_prompt.split("[", 1)[1].split("]", 1)[0]
                ids.add(aid)
            except IndexError:
                pass
    return ids


def resolve_artifact_destination(
    course: Any, course_out: Path, title: str, art_id: str, kind: str
) -> tuple[int | None, ArtifactType, Path]:
    """Determine lecture number, artifact type, and local destination file path.

    Args:
        course: Course entity.
        course_out: Base course output directory.
        title: Artifact title string.
        art_id: Remote artifact identifier.
        kind: Artifact kind string.

    Returns:
        Tuple of (inferred lecture sequence number or None, ArtifactType, destination Path).
    """
    lec_no = infer_lecture_no_from_title(title, len(course.lectures))
    art_type = map_remote_kind_to_artifact_type(kind)

    if lec_no is not None:
        lec = next((item for item in course.lectures if item.no == lec_no), None)
        lec_dir_name = f"{lec_no:02d}_{lec.topic}" if lec else f"lecture_{lec_no:02d}"
        dest_dir = course_out / lec_dir_name
    else:
        dest_dir = course_out / "manual_artifacts"
    dest_dir.mkdir(parents=True, exist_ok=True)

    safe_title = re.sub(r"[^\w\s\-\[\]]", "_", title).strip() or art_id
    ext = get_extension_for_kind(kind)
    output_file = dest_dir / f"{safe_title}{ext}"
    return lec_no, art_type, output_file


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

        existing_jobs = self.queue_repo.list_jobs(course_code=course_code)
        existing_output_files = {j.output_file for j in existing_jobs if j.output_file}
        existing_art_ids = extract_synced_art_ids(existing_jobs)

        for art in remote_artifacts:
            art_id = art["id"]
            title = art["title"]
            kind = art["kind"]

            if art_id in existing_art_ids:
                logger.info("Skipping already synchronized remote artifact %s (%s)", art_id, title)
                continue

            lec_no, art_type, output_file = resolve_artifact_destination(
                course, course_out, title, art_id, kind
            )

            # Check if this artifact is already downloaded or tracked
            if str(output_file) in existing_output_files or output_file.exists():
                logger.info("Artifact file already exists at %s, skipping download", output_file)
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
                    custom_prompt=f"Synced from NotebookLM [{art_id}]: {title}",
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

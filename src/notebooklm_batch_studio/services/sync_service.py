"""Remote synchronization service: syncs manually generated artifacts from Gemini Notebook to local storage.

Queries all remote artifacts in a course's linked Gemini Notebook notebook, identifies artifacts
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
    """Map Gemini Notebook artifact kind string to local domain ArtifactType.

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
    if "concept" in k:
        return ArtifactType.REPORTS_CONCEPT
    return ArtifactType.QUIZ_ACADEMIC


def get_extension_for_kind(kind: str) -> str:
    """Determine file extension based on Gemini Notebook artifact kind.

    Args:
        kind: Artifact kind string.

    Returns:
        Appropriate file extension with leading dot.
    """
    k = kind.lower()
    # Gemini Notebook audio is MP4/AAC and infographics are PNG. Refs: ISSUE-007
    if "audio" in k:
        return ".m4a"
    if "video" in k:
        return ".mp4"
    if "infographic" in k:
        return ".png"
    if "slide" in k:
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
    course: Any, course_out: Path, title: str, **meta: Any
) -> tuple[int | None, ArtifactType, Path]:
    """Determine lecture number, artifact type, and local destination file path.

    Args:
        course: Course entity.
        course_out: Base course output directory.
        title: Artifact title string.
        **meta: Metadata keyword arguments (`art_id`, `kind`).

    Returns:
        Tuple of (inferred lecture sequence number or None, ArtifactType, destination Path).
    """
    art_id = str(meta["art_id"])
    kind = str(meta["kind"])
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
    output_file = dest_dir / f"{safe_title}{get_extension_for_kind(kind)}"
    return lec_no, art_type, output_file


class RemoteSyncService:
    """Synchronizes remote Gemini Notebook artifacts back into local repository and disk."""

    def __init__(
        self,
        notebooklm_client: NotebookLMClientProtocol,
        course_repo: CourseRepositoryProtocol,
        queue_repo: QueueRepositoryProtocol,
        output_base_dir: Path,
    ) -> None:
        """Initialize remote synchronization service.

        Args:
            notebooklm_client: Adapter client for Gemini Notebook communication.
            course_repo: Course repository.
            queue_repo: Job queue repository.
            output_base_dir: Base directory for storing course outputs.
        """
        self.client = notebooklm_client
        self.course_repo = course_repo
        self.queue_repo = queue_repo
        self.output_base_dir = output_base_dir

    async def _download_and_enqueue(
        self, course: Any, art: dict[str, Any], dest: tuple[int | None, Any, Path]
    ) -> dict[str, Any] | None:
        """Download a single remote artifact and record a synthetic DONE job row.

        Args:
            course: Domain Course entity with linked notebook_id.
            art: Remote artifact summary dictionary.
            dest: Tuple of `(lecture_no, ArtifactType, output_file)`.

        Returns:
            Synced metadata dictionary or None on download error.
        """
        lec_no, art_type, output_file = dest
        art_id, title, kind = art["id"], art["title"], art["kind"]
        try:
            downloaded_path = await self.client.download_artifact_by_kind(
                notebook_id=course.notebook_id, artifact_id=art_id, kind=kind, output_path=str(output_file)
            )
            job = ArtifactJob(
                id=str(uuid.uuid4()),
                course_code=course.code,
                lecture_no=lec_no,
                artifact_type=art_type,
                status=JobStatus.DONE,
                output_file=downloaded_path,
                source_origin="remote_sync",
                custom_prompt=f"Synced from Gemini Notebook [{art_id}]: {title}",
            )
            self.queue_repo.enqueue_jobs([job])
            logger.info("Synced remote artifact '%s' to %s", title, downloaded_path)
            return {"id": art_id, "title": title, "path": downloaded_path}
        except Exception as err:
            logger.warning("Failed to sync remote artifact %s (%s): %s", art_id, title, err)
            return None

    async def _sync_single_artifact(
        self, course: Any, art: dict[str, Any], seen: tuple[set[str], set[str]]
    ) -> dict[str, Any] | None:
        """Download and record one remote artifact if not already present locally.

        Args:
            course: Domain Course entity with linked notebook_id.
            art: Remote artifact summary dictionary.
            seen: Tuple of (existing_art_ids, existing_output_files).

        Returns:
            Synced item metadata dictionary, or None when skipped or failed.
        """
        existing_art_ids, existing_output_files = seen
        art_id, title, kind = art["id"], art["title"], art["kind"]
        if art_id in existing_art_ids:
            logger.info("Skipping already synchronized remote artifact %s (%s)", art_id, title)
            return None

        course_out = self.output_base_dir / "courses" / course.code
        lec_no, art_type, output_file = resolve_artifact_destination(
            course, course_out, title, art_id=art_id, kind=kind
        )
        if str(output_file) in existing_output_files or output_file.exists():
            logger.info("Artifact file already exists at %s, skipping download", output_file)
            return None
        return await self._download_and_enqueue(course, art, (lec_no, art_type, output_file))

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
            raise ValueError(f"Course {course_code} has no linked Gemini Notebook notebook")

        logger.info("Syncing remote artifacts for course %s (notebook: %s)", course_code, course.notebook_id)
        remote_artifacts = await self.client.list_artifacts(course.notebook_id)
        existing_jobs = self.queue_repo.list_jobs(course_code=course_code)
        seen = (
            extract_synced_art_ids(existing_jobs),
            {j.output_file for j in existing_jobs if j.output_file},
        )
        synced_items: list[dict[str, Any]] = []
        for art in remote_artifacts:
            item = await self._sync_single_artifact(course, art, seen)
            if item is not None:
                synced_items.append(item)
        return {"course_code": course_code, "synced_count": len(synced_items), "items": synced_items}

    async def list_remote_artifacts(self, course_code: str) -> dict[str, Any]:
        """List remote artifacts for a course and annotate which local versions are in use.

        Args:
            course_code: Course identifier.

        Returns:
            Dictionary with course metadata and annotated remote artifacts.
        """
        course = self.course_repo.get_course(course_code)
        if not course:
            raise ValueError(f"Course not found: {course_code}")
        if not course.notebook_id:
            return {"course_code": course_code, "notebook_id": None, "artifacts": []}
        remote_artifacts = await self.client.list_artifacts(course.notebook_id)
        existing_jobs = self.queue_repo.list_jobs(course_code=course_code)
        by_remote_id, latest_ids = _index_local_artifact_jobs(existing_jobs)
        annotated = [_annotate_remote_artifact(art, by_remote_id, latest_ids) for art in remote_artifacts]
        return {"course_code": course_code, "notebook_id": course.notebook_id, "artifacts": annotated}

    async def delete_remote_artifact(
        self, course_code: str, artifact_id: str, delete_local: bool = False
    ) -> dict[str, Any]:
        """Delete a remote artifact and optionally unlink or remove its local job output.

        Args:
            course_code: Course identifier.
            artifact_id: Remote Gemini Notebook artifact identifier.
            delete_local: Whether to also remove the downloaded local file and mark job skipped.

        Returns:
            Deletion summary dictionary.
        """
        course = self.course_repo.get_course(course_code)
        if not course:
            raise ValueError(f"Course not found: {course_code}")
        if not course.notebook_id:
            raise ValueError(f"Course {course_code} has no linked Gemini Notebook notebook")
        await self.client.delete_artifact(course.notebook_id, artifact_id)
        affected_jobs = self._cleanup_deleted_artifact_jobs(course_code, artifact_id, delete_local)
        logger.info(
            "Deleted remote artifact %s for %s (affected=%s)", artifact_id, course_code, affected_jobs
        )
        return {
            "course_code": course_code,
            "deleted_artifact_id": artifact_id,
            "affected_jobs": affected_jobs,
        }

    def _cleanup_deleted_artifact_jobs(
        self, course_code: str, artifact_id: str, delete_local: bool
    ) -> list[str]:
        """Unlink local jobs pointing to a deleted remote artifact and optionally delete files.

        Args:
            course_code: Course identifier.
            artifact_id: Deleted remote artifact id.
            delete_local: Remove local output file and mark job failed when True.

        Returns:
            List of affected local job ids.
        """
        affected: list[str] = []
        for job in self.queue_repo.list_jobs(course_code=course_code):
            if artifact_id not in _job_remote_ids(job):
                continue
            remaining = [aid for aid in job.artifact_ids if aid != artifact_id]
            self.queue_repo.record_artifact_ids(job.id, remaining)
            if delete_local and job.output_file:
                _remove_local_output(self.output_base_dir, course_code, job.output_file)
                self.queue_repo.fail_job(job.id, "Deleted from remote and local", max_attempts=0)
            affected.append(job.id)
        return affected


def _job_remote_ids(job: ArtifactJob) -> list[str]:
    """Return all remote artifact IDs associated with a local job.

    Args:
        job: ArtifactJob entity.

    Returns:
        List of remote artifact ID strings.
    """
    ids = list(job.artifact_ids or [])
    if job.source_origin == "remote_sync" and job.custom_prompt and "[" in job.custom_prompt:
        try:
            ids.append(job.custom_prompt.split("[", 1)[1].split("]", 1)[0])
        except IndexError:
            pass
    return ids


def _index_local_artifact_jobs(jobs: list[ArtifactJob]) -> tuple[dict[str, ArtifactJob], set[str]]:
    """Index local jobs by remote artifact id and find latest active remote ids per slot.

    Args:
        jobs: All ArtifactJob rows for a course.

    Returns:
        Tuple of (remote_id -> job mapping, set of latest active remote_ids).
    """
    by_remote: dict[str, ArtifactJob] = {}
    latest_by_slot: dict[tuple[int | None, str], ArtifactJob] = {}
    active_statuses = {JobStatus.DONE, JobStatus.NEEDS_REVIEW}
    for job in jobs:
        r_ids = _job_remote_ids(job)
        for rid in r_ids:
            by_remote[rid] = job
        if job.status in active_statuses and r_ids:
            slot = (job.lecture_no, job.artifact_type.value)
            prev = latest_by_slot.get(slot)
            if prev is None or job.version > prev.version:
                latest_by_slot[slot] = job
    latest_ids = {rid for j in latest_by_slot.values() for rid in _job_remote_ids(j)}
    return by_remote, latest_ids


def _annotate_remote_artifact(
    art: dict[str, Any], by_remote: dict[str, ArtifactJob], latest_ids: set[str]
) -> dict[str, Any]:
    """Attach local usage metadata to a remote artifact summary dictionary.

    Args:
        art: Remote artifact summary from client.
        by_remote: Mapping of remote_artifact_id to local ArtifactJob.
        latest_ids: Set of remote_artifact_ids currently active on the study page.

    Returns:
        Enriched remote artifact dictionary.
    """
    art_id = str(art.get("id") or "")
    job = by_remote.get(art_id)
    in_use = bool(job and job.status in {JobStatus.DONE, JobStatus.NEEDS_REVIEW})
    return {
        **art,
        "in_use": in_use,
        "is_latest_active": art_id in latest_ids,
        "local_job_id": job.id if job else None,
        "local_version": job.version if job else None,
        "lecture_no": job.lecture_no if job else None,
        "artifact_type": job.artifact_type.value if job else None,
    }


def _remove_local_output(output_base_dir: Path, course_code: str, rel_path: str) -> None:
    """Safely remove a local artifact output file inside the course output directory.

    Args:
        output_base_dir: Base output directory containing `courses/`.
        course_code: Course identifier.
        rel_path: Course-relative output path.
    """
    course_dir = (output_base_dir / "courses" / course_code).resolve()
    target = (course_dir / rel_path).resolve()
    if target.is_relative_to(course_dir) and target.is_file():
        target.unlink()

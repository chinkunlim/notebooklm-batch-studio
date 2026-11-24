"""Course onboarding & query helpers extracted from the batch orchestrator."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from notebooklm_batch_studio.domain.exceptions import (
    CourseNotFoundError,
    SourceLimitExceededError,
)
from notebooklm_batch_studio.domain.models import (
    Course,
    JobStatus,
    Lecture,
    ProfileName,
)
from notebooklm_batch_studio.domain.study_hierarchy import (
    resolve_course_output_root,
    resolve_lecture_pdf_path,
)
from notebooklm_batch_studio.domain.study_plan import compute_course_study_state
from notebooklm_batch_studio.services.course_parser import scan_course_directory
from notebooklm_batch_studio.services.job_views import (
    calc_job_progress,
    format_jobs_data,
    lecture_to_dict,
    preview_job_types,
)
from notebooklm_batch_studio.services.quota_planner import estimate_quota_plan, read_quota_or_none

if TYPE_CHECKING:
    from notebooklm_batch_studio.config.settings import AppConfig
    from notebooklm_batch_studio.domain.repositories import (
        CourseRepositoryProtocol,
        NotebookLMClientProtocol,
        QueueRepositoryProtocol,
    )
    from notebooklm_batch_studio.services.course_settings import CourseSettingsService

logger = logging.getLogger(__name__)


class CourseOnboardingMixin:
    """Mixin providing folder registration, notebook source setup, and course query views."""

    if TYPE_CHECKING:
        course_repo: CourseRepositoryProtocol
        queue_repo: QueueRepositoryProtocol
        notebooklm_client: NotebookLMClientProtocol
        config: AppConfig
        course_settings: CourseSettingsService

        def enqueue_course_artifacts(self, course_code: str) -> int:
            """Enqueue jobs for a course (implemented by BatchStudioService).

            Args:
                course_code: Course identifier.

            Returns:
                Count of newly enqueued jobs.
            """
            ...

    def register_course_folder(self, folder_path: Path | str) -> Course:
        """Scan a folder, detect course code and lectures, and persist to database.

        Args:
            folder_path: Filesystem path to course directory containing PDFs.

        Returns:
            The saved domain Course entity.
        """
        path = Path(folder_path)
        course = scan_course_directory(path)
        self.course_repo.save_course(course)
        logger.info("Registered course %s with %d lectures", course.code, len(course.lectures))
        return course

    async def _ensure_notebook_id(self, course: Course) -> tuple[str, dict[str, str]]:
        """Resolve or create the Gemini Notebook notebook ID for a course.

        Args:
            course: Course entity.

        Returns:
            Tuple of (notebook_id, existing_sources_mapping).
        """
        existing_sources: dict[str, str] = {}
        if course.notebook_id:
            return course.notebook_id, existing_sources

        # Clean title format: avoid repeating name if code equals or contains name. Refs: ISSUE-037
        title = (
            course.name
            if course.code == course.name or course.code in course.name
            else f"[{course.code}] {course.name}"
        )
        found = await self.notebooklm_client.find_notebook_by_title(title) if course.reuse_notebook else None
        if found:
            notebook_id = found
            existing_sources = await self.notebooklm_client.list_ready_sources(found)
            logger.info("Reusing Gemini Notebook notebook %s for %s", found, course.code)
        else:
            notebook_id = await self.notebooklm_client.create_notebook(title)
            logger.info("Created Gemini Notebook notebook %s for %s", notebook_id, course.code)

        self.course_repo.update_notebook_id(course.code, notebook_id)
        return notebook_id, existing_sources

    async def _perform_lecture_upload(
        self, course_code: str, notebook_id: str, lec: Lecture, pdf_file: Path
    ) -> None:
        """Upload one local PDF file and wait for Gemini Notebook source parsing.

        Args:
            course_code: Course identifier.
            notebook_id: Target Gemini Notebook notebook ID.
            lec: Lecture metadata object.
            pdf_file: Resolved path to the lecture PDF file.
        """
        try:
            self.course_repo.update_lecture_upload_status(course_code, lec.no, "uploading")
            source_id = await self.notebooklm_client.upload_source(notebook_id, str(pdf_file))
            self.course_repo.update_lecture_upload_status(course_code, lec.no, "parsing", source_id=source_id)
            await self.notebooklm_client.wait_source_ready(notebook_id, source_id)
            self.course_repo.update_lecture_upload_status(course_code, lec.no, "ready", source_id=source_id)
            logger.info("Uploaded lecture %d (%s) -> source %s (ready)", lec.no, lec.filename, source_id)
        except Exception as upload_err:
            self.course_repo.update_lecture_upload_status(
                course_code, lec.no, "failed", error_message=str(upload_err)
            )
            logger.exception("Failed to upload lecture %d (%s): %s", lec.no, lec.filename, upload_err)
            raise

    async def _upload_single_lecture(
        self,
        course: Course,
        notebook_id: str,
        lec: Lecture,
        existing_sources: dict[str, str],
    ) -> None:
        """Upload a single lecture PDF to Gemini Notebook or reuse existing source.

        Args:
            course: Associated domain Course entity.
            notebook_id: Target Gemini Notebook notebook ID.
            lec: Lecture metadata object.
            existing_sources: Map of existing filename to source ID.
        """
        if (not lec.source_id or lec.upload_status == "failed") and lec.filename in existing_sources:
            src_id = existing_sources[lec.filename]
            self.course_repo.update_lecture_upload_status(course.code, lec.no, "ready", source_id=src_id)
            logger.info("Lecture %d reuses existing source %s", lec.no, src_id)
            return

        if lec.source_id and lec.upload_status != "failed":
            self.course_repo.update_lecture_upload_status(
                course.code, lec.no, "ready", source_id=lec.source_id
            )
            return

        pdf_file = resolve_lecture_pdf_path(course.source_dir, lec.filename, lec.relative_path)
        if not pdf_file.exists():
            self.course_repo.update_lecture_upload_status(
                course.code, lec.no, "failed", error_message=f"File not found: {lec.filename}"
            )
            return

        await self._perform_lecture_upload(course.code, notebook_id, lec, pdf_file)

    async def setup_notebook_and_sources(self, course_code: str) -> Course:
        """Ensure Google Gemini Notebook notebook is created and all PDFs are uploaded.

        Args:
            course_code: Course code identifier.

        Returns:
            Updated Course entity with notebook_id and source_ids populated.

        Raises:
            CourseNotFoundError: If course code does not exist.
            SourceLimitExceededError: If lectures exceed the account's per-notebook source limit.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")
        await self._check_source_limit(course)

        notebook_id, existing_sources = await self._ensure_notebook_id(course)
        for lec in course.lectures:
            await self._upload_single_lecture(course, notebook_id, lec, existing_sources)

        updated = self.course_repo.get_course(course_code)
        return updated or course

    async def _check_source_limit(self, course: Course) -> None:
        """Refuse courses whose lecture count exceeds Gemini Notebook's per-notebook source limit.

        Args:
            course: Course about to be set up.

        Raises:
            SourceLimitExceededError: When lectures exceed the account's source limit.
        """
        limit = await self.notebooklm_client.get_source_limit()
        if limit is not None and len(course.lectures) > limit:
            raise SourceLimitExceededError(
                f"Course {course.code} has {len(course.lectures)} lectures but this Gemini Notebook "
                f"account allows {limit} sources per notebook; split the course folder"
            )

    def _course_study_state(self, course: Course) -> str:
        """Compute study progress classification ('not_started', 'in_progress', 'finished').

        Args:
            course: Domain Course entity.

        Returns:
            Study state string.
        """
        done_types = {
            (job.lecture_no, job.artifact_type.value)
            for job in self.queue_repo.list_jobs(course_code=course.code, status=JobStatus.DONE)
        }
        getter = getattr(self.course_repo, "get_study_activity", None)
        activity = getter(course.code) if callable(getter) else (set(), set(), set())
        if not (isinstance(activity, tuple) and len(activity) == 3):
            activity = (set(), set(), set())
        return compute_course_study_state([lec.no for lec in course.lectures], done_types, activity)

    def _build_course_summary_row(self, c: Course) -> dict[str, Any]:
        """Build summary metadata dictionary for a single registered course.

        Args:
            c: Domain Course entity.

        Returns:
            Summary dictionary with queue progress and notebook link.
        """
        counts = self.queue_repo.count_by_status(course_code=c.code)
        raw_counts = {st.value: counts.get(st, 0) for st in JobStatus}
        total_jobs, done_jobs, progress_percent = calc_job_progress(raw_counts)
        notebook_url = f"https://notebook.google.com/notebook/{c.notebook_id}" if c.notebook_id else None
        return {
            "code": c.code,
            "name": c.name,
            "profile": c.profile,
            "lecture_count": len(c.lectures),
            "notebook_id": c.notebook_id,
            "notebook_url": notebook_url,
            "total_jobs": total_jobs,
            "done_jobs": done_jobs,
            "progress_percent": progress_percent,
            "counts": raw_counts,
            "paused": c.paused,
            "status": c.status.value,
            "term": c.term,
            "course_no": c.course_no,
            "study_state": self._course_study_state(c),
        }

    def get_courses_summary(self) -> list[dict[str, Any]]:
        """List summary information for all registered courses with queue progress.

        Returns:
            List of dictionary records containing course metadata, lecture count, and progress.
        """
        return [self._build_course_summary_row(c) for c in self.course_repo.list_courses()]

    def _job_progress(self, course_code: str) -> dict[str, Any]:
        """Summarize a course's job counts and completion percentage.

        Args:
            course_code: Course identifier.

        Returns:
            Dictionary with `total_jobs`, `done_jobs`, `progress_percent`, and per-status `counts`.
        """
        counts = self.queue_repo.count_by_status(course_code=course_code)
        raw_counts = {st.value: counts.get(st, 0) for st in JobStatus}
        total_jobs, done_jobs, progress_percent = calc_job_progress(raw_counts)
        return {
            "total_jobs": total_jobs,
            "done_jobs": done_jobs,
            "progress_percent": progress_percent,
            "counts": raw_counts,
        }

    def get_course_detail(self, course_code: str) -> dict[str, Any]:
        """Retrieve detailed progress, lectures, and artifact job records for a course.

        Args:
            course_code: Course identifier (e.g. 'BIO101').

        Returns:
            Dictionary containing complete course profile, lecture list, and artifact jobs.

        Raises:
            CourseNotFoundError: If course code is not registered.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")

        jobs = self.queue_repo.list_jobs(course_code=course_code)
        course_dir = resolve_course_output_root(
            self.config.courses_output_dir, course.code, course.study_dir
        ).resolve()
        notebook_url = (
            f"https://notebook.google.com/notebook/{course.notebook_id}" if course.notebook_id else None
        )
        return {
            "code": course.code,
            "name": course.name,
            "profile": course.profile,
            "notebook_id": course.notebook_id,
            "notebook_url": notebook_url,
            "source_dir": course.source_dir,
            "mock_exam_questions": course.mock_exam_questions,
            **self._job_progress(course_code),
            "paused": course.paused,
            "status": course.status.value,
            "term": course.term,
            "course_no": course.course_no,
            "lectures": [lecture_to_dict(lec) for lec in course.lectures],
            "jobs": format_jobs_data(jobs, course_dir, self.config.needs_review_dir),
        }

    async def _ensure_preview_quota(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Lazily read Gemini Notebook quota once across a folder preview batch.

        Args:
            state: Mutable dict caching `loaded` flag and `data`.

        Returns:
            Quota dictionary or None if unavailable.
        """
        if not state["loaded"]:
            state["data"] = await read_quota_or_none(self.notebooklm_client)
            state["loaded"] = True
        quota: dict[str, Any] | None = state["data"]
        return quota

    async def _preview_single_folder(
        self, raw: str, quota_state: dict[str, Any], filters: tuple[list[str] | None, list[str] | None]
    ) -> dict[str, Any]:
        """Scan and build a preview entry for one candidate course folder.

        Args:
            raw: User-provided directory path string.
            quota_state: Cached quota lookup state across the batch.
            filters: Tuple of (chapter_artifacts, course_artifacts).

        Returns:
            Preview dictionary describing validity, lectures, and quota estimate.
        """
        path = Path(raw).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            return {
                "folder_path": str(path),
                "is_valid": False,
                "error": f"Folder does not exist or is not a directory: {raw}",
            }
        try:
            course = scan_course_directory(path)
            types = preview_job_types(course, filters[0], filters[1])
            plan = estimate_quota_plan(types, await self._ensure_preview_quota(quota_state))  # ISSUE-008
            lecs = [{"no": lec.no, "topic": lec.topic, "filename": lec.filename} for lec in course.lectures]
            return {
                "folder_path": str(path),
                "is_valid": True,
                "error": None,
                "course_code": course.code,
                "course_name": course.name,
                "lecture_count": len(course.lectures),
                "estimated_jobs": len(types),
                **plan,
                "lectures": lecs,
            }
        except Exception as err:
            return {"folder_path": str(path), "is_valid": False, "error": str(err)}

    async def preview_course_folders(
        self,
        folder_paths: list[str],
        chapter_artifacts: list[str] | None = None,
        course_artifacts: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Inspect candidate folders and preview lecture extraction without saving to database.

        Args:
            folder_paths: List of directory paths on the local filesystem.
            chapter_artifacts: Optional custom selected chapter artifact types.
            course_artifacts: Optional custom selected course-wide artifact types.

        Returns:
            List of preview structures detailing course codes, lectures, and quota estimate.
        """
        quota_state: dict[str, Any] = {"loaded": False, "data": None}
        filters = (chapter_artifacts, course_artifacts)
        return [await self._preview_single_folder(raw, quota_state, filters) for raw in folder_paths]

    def _register_single_course_folder(
        self, raw: str, prof_enum: ProfileName, opts: dict[str, Any]
    ) -> dict[str, Any]:
        """Scan, save, apply initial options, and enqueue jobs for one folder.

        Args:
            raw: Filesystem path string for the course folder.
            prof_enum: Resolved ProfileName enum.
            opts: Course registration keyword options.

        Returns:
            Summary dict for the registered course.
        """
        path = Path(raw).expanduser().resolve()
        paused = bool(opts.get("paused", False))
        course = dataclasses.replace(
            scan_course_directory(path),
            profile=prof_enum,
            language=str(opts.get("language", "zh-TW")),
            selected_chapter_artifacts=opts.get("chapter_artifacts") or [],
            selected_course_artifacts=opts.get("course_artifacts") or [],
            paused=paused,
            reuse_notebook=bool(opts.get("reuse_notebook", True)),
        )
        self.course_repo.save_course(course)
        # Hold the course while settings are applied, so no job starts with the old ones.
        self.course_repo.set_course_paused(course.code, True)
        if opts.get("options"):
            self.course_settings.set_options(course.code, opts["options"])
        enqueued = self.enqueue_course_artifacts(course.code)
        self.course_repo.set_course_paused(course.code, paused)
        return {
            "code": course.code,
            "name": course.name,
            "profile": course.profile.value,
            "language": course.language,
            "lecture_count": len(course.lectures),
            "enqueued_jobs": enqueued,
            "paused": paused,
        }

    def add_course_folders(
        self, folder_paths: list[str], profile: str = "full", **options: Any
    ) -> list[dict[str, Any]]:
        """Register course directories and enqueue artifact generation tasks.

        Args:
            folder_paths: List of filesystem paths to course lecture folders.
            profile: Generation profile ('full', 'quiz-only', 'exam-prep').
            **options: Optional `chapter_artifacts`, `course_artifacts`, `language`,
                `paused`, `reuse_notebook`, and `options` dictionary.

        Returns:
            List of dictionaries describing newly registered courses and enqueued job counts.
        """
        prof_enum = ProfileName(profile) if profile in ProfileName._value2member_map_ else ProfileName.FULL
        return [self._register_single_course_folder(raw, prof_enum, options) for raw in folder_paths]

    def list_artifact_files(self, course_code: str, lecture_no: int | None = None) -> list[dict[str, Any]]:
        """List generated deliverable files present on disk for a course.

        Args:
            course_code: Course identifier.
            lecture_no: Optional lecture filter.

        Returns:
            List of file metadata records including filename, relative path, and byte size.
        """
        course = self.course_repo.get_course(course_code)
        study_dir = course.study_dir if course else ""
        course_out = resolve_course_output_root(self.config.courses_output_dir, course_code, study_dir)
        if not course_out.exists():
            return []

        files: list[dict[str, Any]] = []
        prefix = f"{lecture_no:02d}_" if lecture_no is not None else ""
        for path in sorted(course_out.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            rel = path.relative_to(course_out)
            if lecture_no is not None and not rel.parts[0].startswith(prefix):
                continue
            files.append(
                {
                    "filename": path.name,
                    "relative_path": str(rel),
                    "size_bytes": path.stat().st_size,
                    "download_url": f"/api/artifacts/{course_code}/download/{rel}",
                }
            )
        return files

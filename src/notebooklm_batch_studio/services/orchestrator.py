"""Batch orchestrator: coordinates course scanning, task enqueuing, and execution.

Integrates CourseRepository, QueueRepository, NotebookLM client, artifact converters,
and the parallel WorkerPool to provide an end-to-end processing pipeline.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig, load_config
from notebooklm_batch_studio.domain.exceptions import (
    CourseNotFoundError,
    OllamaUnavailableError,
    SourceLimitExceededError,
)
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    Course,
    JobStatus,
    ProfileName,
)
from notebooklm_batch_studio.domain.repositories import (
    CourseRepositoryProtocol,
    NotebookLMClientProtocol,
    OllamaClientProtocol,
    QueueRepositoryProtocol,
)
from notebooklm_batch_studio.services.artifact_runner import ArtifactRunner
from notebooklm_batch_studio.services.course_parser import scan_course_directory
from notebooklm_batch_studio.services.course_settings import CourseSettingsService, apply_job_settings
from notebooklm_batch_studio.services.job_views import (
    format_jobs_data,
    preview_job_types,
)
from notebooklm_batch_studio.services.prompt_generator import PromptGenerator
from notebooklm_batch_studio.services.quiz_reader import read_quiz_content
from notebooklm_batch_studio.services.quota_planner import (
    ensure_quota_for,
    estimate_quota_plan,
    read_quota_or_none,
)
from notebooklm_batch_studio.services.reporter import CourseReporter
from notebooklm_batch_studio.services.sync_service import RemoteSyncService
from notebooklm_batch_studio.services.worker_pool import (
    QueueSessionProvider,
    WorkerPool,
    generate_jobs_for_course,
)

logger = logging.getLogger(__name__)


class BatchStudioService:
    """Core domain service for orchestrating course batch operations."""

    def __init__(
        self,
        course_repo: CourseRepositoryProtocol,
        queue_repo: QueueRepositoryProtocol,
        notebooklm_client: NotebookLMClientProtocol,
        config: AppConfig | None = None,
        queue_provider: QueueSessionProvider | None = None,
        ollama_client: OllamaClientProtocol | None = None,
    ) -> None:
        """Initialize the batch studio service.

        Args:
            course_repo: Repository for course and lecture persistence.
            queue_repo: Repository for task queue state.
            notebooklm_client: Protocol client for NotebookLM operations.
            config: Application configuration.
            queue_provider: Factory returning scoped QueueRepository instances.
            ollama_client: Local Ollama client used for prompt refinement (None disables it).
        """
        self.course_repo = course_repo
        self.queue_repo = queue_repo
        self.notebooklm_client = notebooklm_client
        self.config = config or load_config()
        self.reporter = CourseReporter(self.config.courses_output_dir)
        self.runner = ArtifactRunner(self.notebooklm_client, self.config)
        self.queue_provider = queue_provider or self._default_queue_provider
        self.ollama_client = ollama_client
        self.worker_pool: WorkerPool | None = None
        self._is_queue_running = False
        self.course_settings = CourseSettingsService(course_repo, queue_repo, self.config)

    @contextmanager
    def _default_queue_provider(self) -> Iterator[QueueRepositoryProtocol]:
        """Default fallback queue provider yielding the bound queue repository.

        Yields:
            The bound QueueRepositoryProtocol instance.
        """
        yield self.queue_repo

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

    async def setup_notebook_and_sources(self, course_code: str) -> Course:
        """Ensure Google NotebookLM notebook is created and all PDFs are uploaded.

        Args:
            course_code: Course code identifier.

        Returns:
            Updated Course entity with notebook_id and source_ids populated.

        Raises:
            CourseNotFoundError: If course code does not exist.
            SourceLimitExceededError: If the course has more lectures than the account's
                per-notebook source limit (checked before anything is created or uploaded).
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")
        await self._check_source_limit(course)

        notebook_id = course.notebook_id
        existing_sources: dict[str, str] = {}
        if not notebook_id:
            title = f"[{course.code}] {course.name}"
            found = (
                await self.notebooklm_client.find_notebook_by_title(title) if course.reuse_notebook else None
            )
            if found:
                # Re-adding a course reuses its notebook and already-uploaded PDFs instead of
                # creating a second notebook with the same name.
                notebook_id = found
                existing_sources = await self.notebooklm_client.list_ready_sources(found)
                logger.info("Reusing NotebookLM notebook %s for %s", found, course_code)
            else:
                notebook_id = await self.notebooklm_client.create_notebook(title)
                logger.info("Created NotebookLM notebook %s for %s", notebook_id, course_code)
            self.course_repo.update_notebook_id(course_code, notebook_id)

        for lec in course.lectures:
            if not lec.source_id and lec.filename in existing_sources:
                self.course_repo.update_lecture_upload_status(
                    course_code, lec.no, "ready", source_id=existing_sources[lec.filename]
                )
                logger.info("Lecture %d reuses existing source %s", lec.no, existing_sources[lec.filename])
                continue
            if not lec.source_id:
                pdf_file = Path(course.source_dir) / lec.filename
                if not pdf_file.exists():
                    self.course_repo.update_lecture_upload_status(
                        course_code, lec.no, "failed", error_message=f"File not found: {lec.filename}"
                    )
                    continue

                try:
                    self.course_repo.update_lecture_upload_status(course_code, lec.no, "uploading")
                    source_id = await self.notebooklm_client.upload_source(notebook_id, str(pdf_file))
                    self.course_repo.update_lecture_upload_status(
                        course_code, lec.no, "parsing", source_id=source_id
                    )
                    await self.notebooklm_client.wait_source_ready(notebook_id, source_id)
                    self.course_repo.update_lecture_upload_status(
                        course_code, lec.no, "ready", source_id=source_id
                    )
                    logger.info(
                        "Uploaded lecture %d (%s) -> source %s (ready)", lec.no, lec.filename, source_id
                    )
                except Exception as upload_err:
                    self.course_repo.update_lecture_upload_status(
                        course_code, lec.no, "failed", error_message=str(upload_err)
                    )
                    logger.exception("Failed to upload lecture %d (%s): %s", lec.no, lec.filename, upload_err)
                    raise
            else:
                self.course_repo.update_lecture_upload_status(
                    course_code, lec.no, "ready", source_id=lec.source_id
                )

        updated = self.course_repo.get_course(course_code)
        return updated or course

    async def _check_source_limit(self, course: Course) -> None:
        """Refuse courses whose lecture count exceeds NotebookLM's per-notebook source limit.

        Args:
            course: Course about to be set up.

        Raises:
            SourceLimitExceededError: When lectures exceed the account's source limit.
        """
        limit = await self.notebooklm_client.get_source_limit()
        if limit is not None and len(course.lectures) > limit:
            raise SourceLimitExceededError(
                f"Course {course.code} has {len(course.lectures)} lectures but this NotebookLM "
                f"account allows {limit} sources per notebook; split the course folder"
            )

    async def get_notebooklm_quota(self) -> dict[str, Any]:
        """Return the live NotebookLM usage meter and account limits.

        Returns:
            Quota summary from the NotebookLM adapter.
        """
        return await self.notebooklm_client.get_quota_status()

    def enqueue_course_artifacts(self, course_code: str) -> int:
        """Generate artifact jobs based on active profile and enqueue into database.

        Args:
            course_code: Course code identifier.

        Returns:
            Count of newly added tasks in queue.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")

        jobs = generate_jobs_for_course(course)
        added = self.queue_repo.enqueue_jobs(jobs)
        logger.info("Enqueued %d jobs for course %s", added, course_code)
        return added

    async def execute_job(self, job: ArtifactJob) -> str:
        """Process a single artifact generation task from the queue.

        Args:
            job: The claimed ArtifactJob entity.

        Returns:
            Output file path or review folder path upon completion.

        Raises:
            CourseNotFoundError: When the job's course is missing.
            QuotaExceededError: When the live meter says this action has no quota left.
        """
        course = self.course_repo.get_course(job.course_code)
        if course is None:
            raise CourseNotFoundError(f"Course {job.course_code} not found")
        await ensure_quota_for(self.notebooklm_client, job.artifact_type)
        if not course.notebook_id or any(not lec.source_id for lec in course.lectures):
            logger.info("Initializing NotebookLM notebook and sources for course %s", course.code)
            course = await self.setup_notebook_and_sources(course.code)

        nb_id = course.notebook_id
        if not nb_id:
            raise RuntimeError(f"Course {job.course_code} lacks NotebookLM notebook_id")

        run_job, run_course = apply_job_settings(job, course)  # SPEC-006 (may narrow lectures)
        if job.lecture_no is not None:
            lec = next((item for item in course.lectures if item.no == job.lecture_no), None)
            source_ids = [lec.source_id] if (lec and lec.source_id) else []
            lec_dir_name = f"{job.lecture_no:02d}_{lec.topic if lec else 'lecture'}"
            out_dir = self.config.courses_output_dir / course.code / lec_dir_name
        else:
            source_ids = [item.source_id for item in run_course.lectures if item.source_id]
            out_dir = self.config.courses_output_dir / course.code / "_course_synthesis"

        out_dir.mkdir(parents=True, exist_ok=True)
        path, artifact_ids = await self.runner.process_job_with_ids(
            run_job, run_course, nb_id, source_ids, out_dir
        )
        with self.queue_provider() as repo:
            repo.record_artifact_ids(job.id, artifact_ids)  # Refs: ADR-005
        return path

    def generate_summary(self, course_code: str) -> tuple[Path, Path]:
        """Generate summary.md and summary.html for a given course.

        Args:
            course_code: Course identifier.

        Returns:
            Tuple of (summary_md_path, summary_html_path).
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")

        jobs = self.queue_repo.list_jobs(course_code=course_code)
        status_map: dict[tuple[int | None, str], JobStatus] = {
            (j.lecture_no, j.artifact_type.value): j.status for j in jobs
        }
        return self.reporter.generate_summary(course, status_map)

    def get_courses_summary(self) -> list[dict[str, Any]]:
        """List summary information for all registered courses with queue progress.

        Returns:
            List of dictionary records containing course metadata, lecture count,
            notebook link, and job status counters.
        """
        courses = self.course_repo.list_courses()
        summaries: list[dict[str, Any]] = []
        for c in courses:
            counts = self.queue_repo.count_by_status(course_code=c.code)
            raw_counts = {st.value: counts.get(st, 0) for st in JobStatus}
            total_jobs = sum(raw_counts.values())
            done_jobs = raw_counts.get(JobStatus.DONE.value, 0)
            notebook_url = (
                f"https://notebooklm.google.com/notebook/{c.notebook_id}" if c.notebook_id else None
            )
            summaries.append(
                {
                    "code": c.code,
                    "name": c.name,
                    "profile": c.profile,
                    "lecture_count": len(c.lectures),
                    "notebook_id": c.notebook_id,
                    "notebook_url": notebook_url,
                    "total_jobs": total_jobs,
                    "done_jobs": done_jobs,
                    "progress_percent": round((done_jobs / total_jobs * 100), 1) if total_jobs > 0 else 0.0,
                    "counts": raw_counts,
                    "paused": c.paused,
                }
            )
        return summaries

    def get_course_detail(self, course_code: str) -> dict[str, Any]:
        """Retrieve detailed progress, lectures, and artifact job records for a course.

        Args:
            course_code: Course identifier (e.g. 'BIO101').

        Returns:
            Dictionary containing complete course profile, lecture list, artifact jobs,
            and relative summary links.

        Raises:
            CourseNotFoundError: If course code is not registered.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")

        jobs = self.queue_repo.list_jobs(course_code=course_code)
        counts = self.queue_repo.count_by_status(course_code=course_code)
        raw_counts = {st.value: counts.get(st, 0) for st in JobStatus}
        total_jobs = sum(raw_counts.values())
        done_jobs = raw_counts.get(JobStatus.DONE.value, 0)

        lectures_data = [
            {
                "no": lec.no,
                "topic": lec.topic,
                "filename": lec.filename,
                "source_id": lec.source_id,
                "pdf_hash": lec.sha256,
                "upload_status": lec.upload_status,
                "error_message": lec.error_message,
            }
            for lec in course.lectures
        ]

        course_dir = (self.config.courses_output_dir / course.code).resolve()
        jobs_data = format_jobs_data(jobs, course_dir, self.config.needs_review_dir)

        notebook_url = (
            f"https://notebooklm.google.com/notebook/{course.notebook_id}" if course.notebook_id else None
        )

        return {
            "code": course.code,
            "name": course.name,
            "profile": course.profile,
            "notebook_id": course.notebook_id,
            "notebook_url": notebook_url,
            "source_dir": course.source_dir,
            "mock_exam_questions": course.mock_exam_questions,
            "total_jobs": total_jobs,
            "done_jobs": done_jobs,
            "progress_percent": round((done_jobs / total_jobs * 100), 1) if total_jobs > 0 else 0.0,
            "counts": raw_counts,
            "paused": course.paused,
            "lectures": lectures_data,
            "jobs": jobs_data,
        }

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
            List of preview structures detailing course codes, lecture count, detected files,
            the job count, and a quota estimate from the live meter (see `estimate_quota_plan`).
        """
        results: list[dict[str, Any]] = []
        quota: dict[str, Any] | None = None
        quota_read = False
        for raw in folder_paths:
            path = Path(raw).expanduser().resolve()
            if not path.exists() or not path.is_dir():
                results.append(
                    {
                        "folder_path": str(path),
                        "is_valid": False,
                        "error": f"Folder does not exist or is not a directory: {raw}",
                    }
                )
                continue

            try:
                course = scan_course_directory(path)
                lecture_count = len(course.lectures)
                types = preview_job_types(course, chapter_artifacts, course_artifacts)
                if not quota_read:
                    quota, quota_read = await read_quota_or_none(self.notebooklm_client), True
                plan = estimate_quota_plan(types, quota)  # Refs: ISSUE-008
                results.append(
                    {
                        "folder_path": str(path),
                        "is_valid": True,
                        "error": None,
                        "course_code": course.code,
                        "course_name": course.name,
                        "lecture_count": lecture_count,
                        "estimated_jobs": len(types),
                        **plan,
                        "lectures": [
                            {"no": lec.no, "topic": lec.topic, "filename": lec.filename}
                            for lec in course.lectures
                        ],
                    }
                )
            except Exception as err:
                results.append(
                    {
                        "folder_path": str(path),
                        "is_valid": False,
                        "error": str(err),
                    }
                )
        return results

    def add_course_folders(
        self,
        folder_paths: list[str],
        profile: str = "full",
        chapter_artifacts: list[str] | None = None,
        course_artifacts: list[str] | None = None,
        language: str = "zh-TW",
        paused: bool = False,
        reuse_notebook: bool = True,
        options: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Register course directories and enqueue artifact generation tasks.

        Args:
            folder_paths: List of filesystem paths to course lecture folders.
            profile: Generation profile ('full', 'quiz-only', 'exam-prep').
            chapter_artifacts: Granular list of chapter-level artifact types.
            course_artifacts: Granular list of course-wide aggregated artifact types.
            language: Target output language preference.
            paused: Queue the jobs but hold the course until it is started.
            reuse_notebook: Reuse a NotebookLM notebook with the same title and its PDFs.
            options: Generation options to set before any job runs (see course_settings).

        Returns:
            List of dictionaries describing newly registered courses and enqueued job counts.
        """
        registered: list[dict[str, Any]] = []
        prof_enum = ProfileName(profile) if profile in ProfileName._value2member_map_ else ProfileName.FULL
        for raw in folder_paths:
            path = Path(raw).expanduser().resolve()
            course = scan_course_directory(path)
            course = dataclasses.replace(
                course,
                profile=prof_enum,
                language=language,
                selected_chapter_artifacts=chapter_artifacts or [],
                selected_course_artifacts=course_artifacts or [],
                paused=paused,
                reuse_notebook=reuse_notebook,
            )
            self.course_repo.save_course(course)
            # Hold the course while settings are applied, so no job starts with the old ones.
            self.course_repo.set_course_paused(course.code, True)
            if options:
                self.course_settings.set_options(course.code, options)
            enqueued = self.enqueue_course_artifacts(course.code)
            self.course_repo.set_course_paused(course.code, paused)
            registered.append(
                {
                    "code": course.code,
                    "name": course.name,
                    "profile": course.profile.value,
                    "language": course.language,
                    "lecture_count": len(course.lectures),
                    "enqueued_jobs": enqueued,
                    "paused": paused,
                }
            )
        return registered

    def get_quiz_content(
        self, course_code: str, lecture_no: int, variant: str, with_answers: bool = False
    ) -> dict[str, Any]:
        """Locate and read generated quiz content for a specific lecture.

        Args:
            course_code: Course code identifier.
            lecture_no: Sequence number of the lecture.
            variant: Quiz variant ('1-基礎', '2-理解', '3-模擬考', 'quiz_1', 'quiz_2', 'quiz_3').
            with_answers: If False, returns questions-only markdown; if True, includes answer key.

        Returns:
            Dictionary containing quiz metadata, question count, and content text.

        Raises:
            CourseNotFoundError: If course does not exist.
            FileNotFoundError: If the quiz files have not yet been produced.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")

        return read_quiz_content(self.config.courses_output_dir, course, lecture_no, variant, with_answers)

    def list_artifact_files(self, course_code: str, lecture_no: int | None = None) -> list[dict[str, Any]]:
        """List generated deliverable files present on disk for a course.

        Args:
            course_code: Course identifier.
            lecture_no: Optional lecture filter.

        Returns:
            List of file metadata records including filename, relative path, and byte size.
        """
        course_out = self.config.courses_output_dir / course_code
        if not course_out.exists():
            return []

        files: list[dict[str, Any]] = []
        prefix = f"{lecture_no:02d}_" if lecture_no is not None else ""

        for path in sorted(course_out.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                rel = path.relative_to(course_out)
                parts = rel.parts
                if lecture_no is not None:
                    if not parts[0].startswith(prefix):
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

    def retry_job(self, job_id: str) -> bool:
        """Reset a failed or cancelled task back to pending.

        Args:
            job_id: Task UUID.

        Returns:
            True if task was reset, False if job not found.
        """
        return self.queue_repo.retry_job(job_id)

    def resume_quota_wait(self) -> int:
        """Wake all quota-blocked tasks back to pending.

        Returns:
            Number of awakened jobs.
        """
        return self.queue_repo.refresh_quota_wait()

    def set_course_profile(self, course_code: str, profile: str) -> dict[str, Any]:
        """Update active profile for a course and enqueue missing jobs.

        Args:
            course_code: Course identifier.
            profile: New profile name.

        Returns:
            Updated course summary.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")

        prof_enum = ProfileName(profile)
        self.course_repo.update_profile(course_code, prof_enum.value)
        course = dataclasses.replace(course, profile=prof_enum)
        new_jobs = generate_jobs_for_course(course)
        enqueued = self.queue_repo.enqueue_jobs(new_jobs)
        return {
            "course_code": course_code,
            "profile": prof_enum.value,
            "new_jobs_enqueued": enqueued,
        }

    def check_auth_status(self) -> dict[str, Any]:
        """Check NotebookLM credential readiness.

        Returns:
            Dictionary indicating whether login state file is valid.
        """
        storage_path = str(self.config.notebooklm_home / "profiles" / "default" / "storage_state.json")
        has_auth = False
        if hasattr(self.notebooklm_client, "check_auth"):
            has_auth = bool(self.notebooklm_client.check_auth())
        else:
            has_auth = Path(storage_path).exists()
        return {
            "authenticated": has_auth,
            "storage_path": storage_path,
        }

    def is_queue_running(self) -> bool:
        """Check if queue execution is currently active.

        Returns:
            True if running and not paused, False otherwise.
        """
        if self.worker_pool is not None:
            return self.worker_pool._running and not self.worker_pool.is_paused
        return self._is_queue_running

    def pause_queue(self) -> bool:
        """Pause active queue processing gracefully.

        Returns:
            True upon pause request.
        """
        self._is_queue_running = False
        if self.worker_pool:
            self.worker_pool.pause()
            logger.info("WorkerPool paused gracefully.")
        return True

    def resume_queue(self) -> bool:
        """Resume active queue processing.

        Returns:
            True upon resume request.
        """
        self._is_queue_running = True
        if self.worker_pool:
            self.worker_pool.resume()
            logger.info("WorkerPool resumed.")
        else:
            self.start_queue()
        return True

    def start_queue(self) -> bool:
        """Start active queue processing.

        Returns:
            True upon start request.
        """
        self._is_queue_running = True
        if self.worker_pool and self.worker_pool.is_paused:
            self.worker_pool.resume()
            return True

        try:
            loop = asyncio.get_running_loop()
            if not loop.is_closed():
                if self.worker_pool is None:
                    self.worker_pool = WorkerPool(
                        queue_provider=self.queue_provider,
                        executor=self.execute_job,
                        concurrency=2,
                    )
                if not self.worker_pool._running:
                    loop.create_task(self.worker_pool.start())
                    logger.info("WorkerPool background start scheduled.")
        except RuntimeError:
            pass
        return True

    def update_job_prompt(self, job_id: str, prompt: str) -> bool:
        """Update customized prompt for an artifact generation job.

        Args:
            job_id: Task UUID.
            prompt: Customized prompt string.

        Returns:
            True if updated, False otherwise.
        """
        return self.queue_repo.update_job_prompt(job_id, prompt)

    def refine_course_prompts_with_ollama(self, course_code: str) -> int:
        """Rewrite prompts of a course's unfinished jobs using local Ollama.

        DONE and RUNNING jobs are skipped; only prompts that actually changed are counted.
        Refs: ISSUE-001

        Args:
            course_code: Course identifier.

        Returns:
            Count of prompts that were replaced by an Ollama-refined version.

        Raises:
            CourseNotFoundError: If the course does not exist.
            OllamaUnavailableError: If no Ollama client is configured or it is unreachable.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")
        if self.ollama_client is None or not self.ollama_client.is_available():
            raise OllamaUnavailableError(
                "Ollama is not configured or not reachable; prompts were not changed"
            )

        prompt_gen = PromptGenerator(self.ollama_client)
        skip = (JobStatus.DONE, JobStatus.RUNNING)
        jobs = [j for j in self.queue_repo.list_jobs(course_code=course_code) if j.status not in skip]
        updated_count = 0
        for j in jobs:
            lec = next((item for item in course.lectures if item.no == j.lecture_no), None)
            topic = lec.topic if lec else "全範圍整合"
            base = prompt_gen.get_base_blueprint_prompt(j.artifact_type, topic, course.name, course.language)
            refined = prompt_gen.generate_refined_prompt(
                j.artifact_type, topic, course.name, course.language, use_ollama=True
            )
            if refined and refined != base and self.queue_repo.update_job_prompt(j.id, refined):
                updated_count += 1
        logger.info("Refined %d/%d prompts with Ollama for course %s", updated_count, len(jobs), course_code)
        return updated_count

    async def sync_course_artifacts(self, course_code: str) -> dict[str, Any]:
        """Synchronize remote NotebookLM artifacts back to local storage and database.

        Args:
            course_code: Course identifier.

        Returns:
            Dictionary summary with count and synced item metadata.
        """
        sync_service = RemoteSyncService(
            notebooklm_client=self.notebooklm_client,
            course_repo=self.course_repo,
            queue_repo=self.queue_repo,
            output_base_dir=self.config.output_dir,
        )
        return await sync_service.sync_course(course_code)

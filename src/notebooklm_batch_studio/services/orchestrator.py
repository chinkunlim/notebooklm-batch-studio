"""Batch orchestrator: coordinates course scanning, task enqueuing, and execution.

Integrates CourseRepository, QueueRepository, NotebookLM client, artifact converters,
and the parallel WorkerPool to provide an end-to-end processing pipeline.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig, load_config
from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    JobStatus,
    ProfileName,
    Quiz,
)
from notebooklm_batch_studio.domain.repositories import (
    CourseRepositoryProtocol,
    NotebookLMClientProtocol,
    QueueRepositoryProtocol,
)
from notebooklm_batch_studio.services.converters.flashcard_converter import (
    parse_notebooklm_flashcards,
    to_anki_csv,
)
from notebooklm_batch_studio.services.converters.flashcard_converter import (
    to_json as flashcards_to_json,
)
from notebooklm_batch_studio.services.converters.mindmap_converter import (
    parse_notebooklm_mindmap,
    to_opml,
)
from notebooklm_batch_studio.services.converters.mindmap_converter import (
    to_json as mindmap_to_json,
)
from notebooklm_batch_studio.services.converters.mindmap_converter import (
    to_markdown as mindmap_to_markdown,
)
from notebooklm_batch_studio.services.converters.quiz_converter import (
    merge_and_deduplicate_quizzes,
    parse_notebooklm_quiz,
    to_answer_markdown,
    to_exam_markdown,
    to_pdf,
)
from notebooklm_batch_studio.services.converters.quiz_converter import (
    to_json as quiz_to_json,
)
from notebooklm_batch_studio.services.course_parser import scan_course_directory
from notebooklm_batch_studio.services.reporter import CourseReporter
from notebooklm_batch_studio.services.worker_pool import generate_jobs_for_course

logger = logging.getLogger(__name__)


class BatchStudioService:
    """Core domain service for orchestrating course batch operations."""

    def __init__(
        self,
        course_repo: CourseRepositoryProtocol,
        queue_repo: QueueRepositoryProtocol,
        notebooklm_client: NotebookLMClientProtocol,
        config: AppConfig | None = None,
    ) -> None:
        """Initialize the batch studio service.

        Args:
            course_repo: Repository for course and lecture persistence.
            queue_repo: Repository for task queue state.
            notebooklm_client: Protocol client for NotebookLM operations.
            config: Application configuration.
        """
        self.course_repo = course_repo
        self.queue_repo = queue_repo
        self.notebooklm_client = notebooklm_client
        self.config = config or load_config()
        self.reporter = CourseReporter(self.config.courses_output_dir)

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
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")

        notebook_id = course.notebook_id
        if not notebook_id:
            title = f"[{course.code}] {course.name}"
            notebook_id = await self.notebooklm_client.create_notebook(title)
            self.course_repo.update_notebook_id(course_code, notebook_id)
            logger.info("Created NotebookLM notebook %s for %s", notebook_id, course_code)

        for lec in course.lectures:
            if not lec.source_id:
                pdf_file = Path(course.source_dir) / lec.filename
                if pdf_file.exists():
                    source_id = await self.notebooklm_client.upload_source(notebook_id, str(pdf_file))
                    await self.notebooklm_client.wait_source_ready(notebook_id, source_id)
                    self.course_repo.update_lecture_source_id(course_code, lec.no, source_id)
                    logger.info("Uploaded lecture %d (%s) -> source %s", lec.no, lec.filename, source_id)

        updated = self.course_repo.get_course(course_code)
        return updated or course

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
        """
        course = self.course_repo.get_course(job.course_code)
        if course is None:
            raise CourseNotFoundError(f"Course {job.course_code} not found")
        if not course.notebook_id:
            raise RuntimeError(f"Course {job.course_code} lacks NotebookLM notebook_id")

        nb_id = course.notebook_id

        if job.lecture_no is not None:
            lec = next((item for item in course.lectures if item.no == job.lecture_no), None)
            source_ids = [lec.source_id] if (lec and lec.source_id) else []
            lec_dir_name = f"{job.lecture_no:02d}_{lec.topic if lec else 'lecture'}"
            out_dir = self.config.courses_output_dir / course.code / lec_dir_name
        else:
            source_ids = [item.source_id for item in course.lectures if item.source_id]
            is_exam = job.artifact_type == ArtifactType.COURSE_MOCK_EXAM
            sub_folder = "_course_exam" if is_exam else "_course_mindmap"
            out_dir = self.config.courses_output_dir / course.code / sub_folder

        out_dir.mkdir(parents=True, exist_ok=True)

        if job.artifact_type == ArtifactType.AUDIO:
            return await self._process_audio(job, nb_id, source_ids, out_dir)
        if job.artifact_type in (ArtifactType.QUIZ_1, ArtifactType.QUIZ_2, ArtifactType.QUIZ_3):
            return await self._process_quiz(job, course, nb_id, source_ids, out_dir)
        if job.artifact_type == ArtifactType.FLASHCARDS:
            return await self._process_flashcards(job, course, nb_id, source_ids, out_dir)
        if job.artifact_type == ArtifactType.MIND_MAP:
            return await self._process_mindmap(job, nb_id, source_ids, out_dir)
        if job.artifact_type == ArtifactType.COURSE_MOCK_EXAM:
            return await self._process_mock_exam(job, course, nb_id, source_ids, out_dir)
        if job.artifact_type == ArtifactType.COURSE_MIND_MAP:
            return await self._process_mindmap(job, nb_id, source_ids, out_dir, is_course_wide=True)

        raise ValueError(f"Unsupported artifact type: {job.artifact_type}")

    async def _process_audio(self, job: ArtifactJob, nb_id: str, source_ids: list[str], out_dir: Path) -> str:
        """Generate and save Deep Dive Audio MP3.

        Args:
            job: Current artifact job.
            nb_id: NotebookLM notebook identifier.
            source_ids: List of source identifiers to include.
            out_dir: Target output directory for files.

        Returns:
            Path string of the saved audio file.
        """
        await self.notebooklm_client.generate_audio(nb_id, source_ids)
        audio_file = out_dir / f"{job.course_code}_L{job.lecture_no:02d}_audio.mp3"
        await self.notebooklm_client.download_audio(nb_id, str(audio_file))
        return str(audio_file)

    async def _process_quiz(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> str:
        """Generate 30-question quiz with deduplication, markdown, and PDF output.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers for the lecture.
            out_dir: Target output directory.

        Returns:
            Path string to the resulting quiz.json or quarantined file.
        """
        variant_map = {
            ArtifactType.QUIZ_1: "1-基礎",
            ArtifactType.QUIZ_2: "2-理解",
            ArtifactType.QUIZ_3: "3-模擬考",
        }
        variant = variant_map.get(job.artifact_type, "1-基礎")
        batches: list[Quiz] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            for attempt in range(3):
                tmp_json = Path(tmp_dir) / f"quiz_attempt_{attempt}.json"
                await self.notebooklm_client.generate_quiz(
                    nb_id, source_ids, prompt=f"Generate rigorous questions for {variant}"
                )
                await self.notebooklm_client.download_quiz(nb_id, str(tmp_json))

                if tmp_json.exists():
                    raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))
                    parsed = parse_notebooklm_quiz(
                        raw_data=raw_data,
                        course_code=course.code,
                        lecture_no=job.lecture_no or 0,
                        variant=variant,
                        source_pdf=f"{job.lecture_no:02d}.pdf",
                    )
                    batches.append(parsed)

                merged, is_complete = merge_and_deduplicate_quizzes(batches, target_count=30)
                if is_complete:
                    break

        merged_quiz, is_complete = merge_and_deduplicate_quizzes(batches, target_count=30)
        if not is_complete:
            review_dir = self.config.needs_review_dir / f"{course.code}_L{job.lecture_no}_{variant}"
            review_dir.mkdir(parents=True, exist_ok=True)
            incomplete_json = review_dir / "quiz.json"
            incomplete_json.write_text(quiz_to_json(merged_quiz), encoding="utf-8")
            logger.warning(
                "Quiz incomplete (%d questions), quarantined to %s",
                len(merged_quiz.questions),
                review_dir,
            )
            return str(incomplete_json)

        return _save_quiz_files(out_dir, merged_quiz)

    async def _process_flashcards(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> str:
        """Generate flashcards and save JSON and Anki CSV.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers.
            out_dir: Target output directory.

        Returns:
            Path string of saved anki.csv.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_json = Path(tmp_dir) / "flashcards.json"
            await self.notebooklm_client.generate_flashcards(nb_id, source_ids)
            await self.notebooklm_client.download_flashcards(nb_id, str(tmp_json))
            raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))

        cards = parse_notebooklm_flashcards(raw_data)
        fc_json = out_dir / "flashcards.json"
        anki_csv = out_dir / "anki.csv"

        title = f"[{course.code}] L{job.lecture_no}"
        fc_json.write_text(flashcards_to_json(cards, title=title), encoding="utf-8")
        anki_tags = [course.code, f"L{job.lecture_no:02d}"]
        anki_csv.write_text(to_anki_csv(cards, tags=anki_tags), encoding="utf-8")
        return str(anki_csv)

    async def _process_mindmap(
        self, job: ArtifactJob, nb_id: str, source_ids: list[str], out_dir: Path, is_course_wide: bool = False
    ) -> str:
        """Generate mind map and export to JSON, OPML 2.0 XML, and Markdown.

        Args:
            job: Current artifact job.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers.
            out_dir: Target output directory.
            is_course_wide: Whether generating course-wide or lecture-level mind map.

        Returns:
            Path string of saved mindmap.opml.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_json = Path(tmp_dir) / "mindmap.json"
            await self.notebooklm_client.generate_mind_map(nb_id, source_ids)
            await self.notebooklm_client.download_mind_map(nb_id, str(tmp_json))
            raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))

        root = parse_notebooklm_mindmap(raw_data)
        mm_json = out_dir / "mindmap.json"
        mm_opml = out_dir / "mindmap.opml"
        mm_md = out_dir / "mindmap.md"

        mm_json.write_text(mindmap_to_json(root), encoding="utf-8")
        mm_opml.write_text(to_opml(root), encoding="utf-8")
        mm_md.write_text(mindmap_to_markdown(root), encoding="utf-8")
        return str(mm_opml)

    async def _process_mock_exam(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> str:
        """Generate course-wide 50-question mock exam across all lecture sources.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: All source identifiers belonging to the course.
            out_dir: Target output directory.

        Returns:
            Path string to resulting quiz.json.
        """
        target_q = course.mock_exam_questions or 50
        batches: list[Quiz] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            for attempt in range(5):
                tmp_json = Path(tmp_dir) / f"mock_attempt_{attempt}.json"
                await self.notebooklm_client.generate_quiz(
                    nb_id, source_ids, prompt=f"Comprehensive course final exam, batch {attempt + 1}"
                )
                await self.notebooklm_client.download_quiz(nb_id, str(tmp_json))
                if tmp_json.exists():
                    raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))
                    batches.append(
                        parse_notebooklm_quiz(
                            raw_data=raw_data,
                            course_code=course.code,
                            lecture_no=0,
                            variant="模擬考",
                            title=f"[{course.code}] 全課程期末模擬考",
                        )
                    )
                merged, is_complete = merge_and_deduplicate_quizzes(batches, target_count=target_q)
                if is_complete:
                    break

        final_quiz, _ = merge_and_deduplicate_quizzes(batches, target_count=target_q)
        return _save_quiz_files(out_dir, final_quiz)

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
            }
            for lec in course.lectures
        ]

        jobs_data = [
            {
                "id": j.id,
                "lecture_no": j.lecture_no,
                "artifact_type": j.artifact_type.value,
                "status": j.status.value,
                "output_file": j.output_file,
                "error_message": j.error_message,
                "attempts": j.attempts,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            }
            for j in jobs
        ]

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
            "lectures": lectures_data,
            "jobs": jobs_data,
        }

    def preview_course_folders(self, folder_paths: list[str]) -> list[dict[str, Any]]:
        """Inspect candidate folders and preview lecture extraction without saving to database.

        Args:
            folder_paths: List of directory paths on the local filesystem.

        Returns:
            List of preview structures detailing course codes, lecture count, detected files,
            and estimated artifact workload.
        """
        results: list[dict[str, Any]] = []
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
                estimated_jobs = lecture_count * 6 + 2 if lecture_count > 0 else 0
                estimated_days = max(1, round(estimated_jobs / 100 + 0.49))
                results.append(
                    {
                        "folder_path": str(path),
                        "is_valid": True,
                        "error": None,
                        "course_code": course.code,
                        "course_name": course.name,
                        "lecture_count": lecture_count,
                        "estimated_jobs": estimated_jobs,
                        "estimated_days": estimated_days,
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

    def add_course_folders(self, folder_paths: list[str], profile: str = "full") -> list[dict[str, Any]]:
        """Register course directories and enqueue artifact generation tasks.

        Args:
            folder_paths: List of filesystem paths to course lecture folders.
            profile: Generation profile ('full', 'quiz-only', 'exam-prep').

        Returns:
            List of dictionaries describing newly registered courses and enqueued job counts.
        """
        registered: list[dict[str, Any]] = []
        prof_enum = ProfileName(profile)
        for raw in folder_paths:
            path = Path(raw).expanduser().resolve()
            course = scan_course_directory(path)
            course = dataclasses.replace(course, profile=prof_enum)
            self.course_repo.save_course(course)
            enqueued = self.enqueue_course_artifacts(course.code)
            registered.append(
                {
                    "code": course.code,
                    "name": course.name,
                    "profile": course.profile.value,
                    "lecture_count": len(course.lectures),
                    "enqueued_jobs": enqueued,
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

        lec = next((item for item in course.lectures if item.no == lecture_no), None)
        lec_topic = lec.topic if lec else "lecture"
        lec_dir_name = f"{lecture_no:02d}_{lec_topic}"
        quiz_dir = self.config.courses_output_dir / course.code / lec_dir_name

        md_filename = "答案卷.md" if with_answers else "題目卷.md"
        md_file = quiz_dir / md_filename
        json_file = quiz_dir / "quiz.json"

        if not md_file.exists():
            raise FileNotFoundError(f"Quiz artifact not found for {course_code} L{lecture_no} ({variant})")

        return {
            "course_code": course_code,
            "lecture_no": lecture_no,
            "variant": variant,
            "with_answers": with_answers,
            "markdown": md_file.read_text(encoding="utf-8"),
            "json_data": json.loads(json_file.read_text(encoding="utf-8")) if json_file.exists() else None,
        }

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
            True if running, False if idle or paused.
        """
        return getattr(self, "_is_queue_running", False)

    def pause_queue(self) -> bool:
        """Pause active queue processing.

        Returns:
            True.
        """
        self._is_queue_running = False
        return True

    def start_queue(self) -> bool:
        """Start active queue processing.

        Returns:
            True.
        """
        self._is_queue_running = True
        return True


def _save_quiz_files(out_dir: Path, quiz: Quiz) -> str:
    """Save quiz markdown, JSON, and PDF files to target directory.

    Args:
        out_dir: Destination folder.
        quiz: Domain Quiz entity.

    Returns:
        Path string of quiz.json.
    """
    exam_md = out_dir / "題目卷.md"
    ans_md = out_dir / "答案卷.md"
    final_json = out_dir / "quiz.json"
    exam_pdf = out_dir / "題目卷.pdf"
    ans_pdf = out_dir / "答案卷.pdf"

    exam_md.write_text(to_exam_markdown(quiz), encoding="utf-8")
    ans_md.write_text(to_answer_markdown(quiz), encoding="utf-8")
    final_json.write_text(quiz_to_json(quiz), encoding="utf-8")
    to_pdf(quiz, exam_pdf, is_answer_key=False)
    to_pdf(quiz, ans_pdf, is_answer_key=True)

    return str(final_json)

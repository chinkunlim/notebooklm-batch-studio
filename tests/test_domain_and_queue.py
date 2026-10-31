"""Unit tests for domain models, CourseRepository, QueueRepository, and WorkerPool."""

from __future__ import annotations

import asyncio
import unittest
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.domain.exceptions import QuotaExceededError
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    JobStatus,
    Lecture,
    ProfileName,
    get_artifact_english_title,
    get_course_range_prefix,
    get_lecture_prefix,
)
from notebooklm_batch_studio.domain.repositories import QueueRepositoryProtocol
from notebooklm_batch_studio.services.prompt_generator import PromptGenerator
from notebooklm_batch_studio.services.worker_pool import WorkerPool, generate_jobs_for_course


class DomainAndQueueTest(unittest.IsolatedAsyncioTestCase):
    """Verify course persistence, queue state transitions, and worker quota isolation."""

    def setUp(self) -> None:
        """Create an in-memory SQLite database and sessionmaker."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

    def tearDown(self) -> None:
        """Tear down database tables."""
        Base.metadata.drop_all(self.engine)

    def test_course_repository_save_and_retrieve(self) -> None:
        """A course with lectures can be saved and retrieved as pure domain objects."""
        with self.session_factory() as session:
            repo = CourseRepository(session)
            course = Course(
                code="BIO101",
                name="普通生物學",
                source_dir="/tmp/bio101",
                profile=ProfileName.FULL,
                lectures=[
                    Lecture(no=1, topic="細胞構造", filename="01_cell.pdf", sha256="hash1"),
                    Lecture(no=2, topic="能量代謝", filename="02_energy.pdf", sha256="hash2"),
                ],
            )
            repo.save_course(course)
            session.commit()

        with self.session_factory() as session:
            repo = CourseRepository(session)
            retrieved = repo.get_course("BIO101")
            self.assertIsNotNone(retrieved)
            assert retrieved is not None
            self.assertEqual(retrieved.code, "BIO101")
            self.assertEqual(retrieved.name, "普通生物學")
            self.assertEqual(len(retrieved.lectures), 2)
            self.assertEqual(retrieved.lectures[0].topic, "細胞構造")

            # Update notebook_id
            repo.update_notebook_id("BIO101", "nb-12345")
            session.commit()

        with self.session_factory() as session:
            repo = CourseRepository(session)
            updated = repo.get_course("BIO101")
            assert updated is not None
            self.assertEqual(updated.notebook_id, "nb-12345")

    def test_job_generation_matrix(self) -> None:
        """Full profile generates all 8 lecture artifacts plus 2 course-wide artifacts."""
        course = Course(
            code="CHEM201",
            name="有機化學",
            source_dir="/tmp/chem201",
            profile=ProfileName.FULL,
            lectures=[
                Lecture(no=1, topic="烷類", filename="01_alkanes.pdf", sha256="h1"),
                Lecture(no=2, topic="烯類", filename="02_alkenes.pdf", sha256="h2"),
            ],
        )
        jobs = generate_jobs_for_course(course)
        # 2 lectures * 8 artifacts + 2 course-wide = 18 jobs
        self.assertEqual(len(jobs), 18)

        # Check QUIZ_ONLY profile
        quiz_course = Course(
            code="CHEM201",
            name="有機化學",
            source_dir="/tmp/chem201",
            profile=ProfileName.QUIZ_ONLY,
            lectures=[Lecture(no=1, topic="烷類", filename="01_alkanes.pdf", sha256="h1")],
        )
        quiz_jobs = generate_jobs_for_course(quiz_course)
        # 1 lecture * 4 artifacts = 4 jobs
        self.assertEqual(len(quiz_jobs), 4)

    def test_queue_enqueue_and_deduplication(self) -> None:
        """Enqueueing duplicate jobs for the same lecture artifact type is ignored."""
        with self.session_factory() as session:
            repo = QueueRepository(session)
            jobs = [
                ArtifactJob(
                    id="job-1", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1
                ),
                ArtifactJob(
                    id="job-2", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_2
                ),
            ]
            added_first = repo.enqueue_jobs(jobs)
            self.assertEqual(added_first, 2)

            # Re-enqueue the same jobs with different IDs
            duplicate_jobs = [
                ArtifactJob(
                    id="job-3", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1
                ),
                ArtifactJob(
                    id="job-4", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.FLASHCARDS
                ),
            ]
            added_second = repo.enqueue_jobs(duplicate_jobs)
            # Only FLASHCARDS is new
            self.assertEqual(added_second, 1)
            session.commit()

    def test_atomic_claim_and_completion(self) -> None:
        """Workers claim pending jobs sequentially and transition states cleanly."""
        with self.session_factory() as session:
            repo = QueueRepository(session)
            repo.enqueue_jobs(
                [
                    ArtifactJob(
                        id="j-1", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1
                    ),
                    ArtifactJob(
                        id="j-2", course_code="BIO101", lecture_no=2, artifact_type=ArtifactType.QUIZ_1
                    ),
                ]
            )
            session.commit()

        # Worker 1 claims job 1
        with self.session_factory() as session:
            repo = QueueRepository(session)
            claimed1 = repo.claim_next_job("worker-1")
            self.assertIsNotNone(claimed1)
            assert claimed1 is not None
            self.assertEqual(claimed1.id, "j-1")
            self.assertEqual(claimed1.status, JobStatus.RUNNING)
            self.assertEqual(claimed1.worker_id, "worker-1")
            session.commit()

        # Worker 2 claims job 2
        with self.session_factory() as session:
            repo = QueueRepository(session)
            claimed2 = repo.claim_next_job("worker-2")
            self.assertIsNotNone(claimed2)
            assert claimed2 is not None
            self.assertEqual(claimed2.id, "j-2")
            session.commit()

        # Complete job 1
        with self.session_factory() as session:
            repo = QueueRepository(session)
            repo.complete_job("j-1", "/output/bio101/01_Quiz1.json")
            session.commit()

        with self.session_factory() as session:
            repo = QueueRepository(session)
            done_job = repo.get_job("j-1")
            assert done_job is not None
            self.assertEqual(done_job.status, JobStatus.DONE)
            self.assertEqual(done_job.output_file, "/output/bio101/01_Quiz1.json")

    def test_quota_wait_isolation_and_resume(self) -> None:
        """When AUDIO hits quota limit, only AUDIO is blocked; other artifact types proceed."""
        with self.session_factory() as session:
            repo = QueueRepository(session)
            repo.enqueue_jobs(
                [
                    ArtifactJob(
                        id="j-audio", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.AUDIO
                    ),
                    ArtifactJob(
                        id="j-quiz", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1
                    ),
                ]
            )
            session.commit()

        # Audio encounters quota limit
        with self.session_factory() as session:
            repo = QueueRepository(session)
            repo.block_job_quota("j-audio", ArtifactType.AUDIO, cooldown_seconds=3600)
            session.commit()

        # Next claim with AUDIO in excluded types
        with self.session_factory() as session:
            repo = QueueRepository(session)
            # Worker claiming while AUDIO is blocked
            next_job = repo.claim_next_job("worker-1", excluded_types={ArtifactType.AUDIO})
            self.assertIsNotNone(next_job)
            assert next_job is not None
            self.assertEqual(next_job.artifact_type, ArtifactType.QUIZ_1)
            session.commit()

        # Check status counts
        with self.session_factory() as session:
            repo = QueueRepository(session)
            counts = repo.count_by_status("BIO101")
            self.assertEqual(counts[JobStatus.QUOTA_WAIT], 1)
            self.assertEqual(counts[JobStatus.RUNNING], 1)

            # Trigger quota refresh
            awakened = repo.refresh_quota_wait(artifact_type=ArtifactType.AUDIO)
            self.assertEqual(awakened, 1)
            session.commit()

        with self.session_factory() as session:
            repo = QueueRepository(session)
            refreshed_job = repo.get_job("j-audio")
            assert refreshed_job is not None
            self.assertEqual(refreshed_job.status, JobStatus.PENDING)

    async def test_worker_pool_parallel_processing(self) -> None:
        """WorkerPool executes jobs concurrently across workers and isolates quota limit."""
        with self.session_factory() as session:
            repo = QueueRepository(session)
            repo.enqueue_jobs(
                [
                    ArtifactJob(
                        id="j-1", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1
                    ),
                    ArtifactJob(
                        id="j-2", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.AUDIO
                    ),
                    ArtifactJob(
                        id="j-3", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.FLASHCARDS
                    ),
                ]
            )
            session.commit()

        executed_jobs: list[str] = []

        async def mock_executor(job: ArtifactJob) -> str:
            if job.artifact_type == ArtifactType.AUDIO:
                raise QuotaExceededError(
                    "Audio daily quota reached", artifact_type="audio", retry_after_seconds=10
                )
            executed_jobs.append(job.artifact_type.value)
            await asyncio.sleep(0.01)
            return f"/mock/{job.artifact_type.value}.out"

        @contextmanager
        def queue_provider() -> Generator[QueueRepositoryProtocol, None, None]:
            with self.session_factory() as session:
                yield QueueRepository(session)
                session.commit()

        pool = WorkerPool(queue_provider, mock_executor, concurrency=2, probe_interval_seconds=0.1)
        await pool.start()
        # Allow workers to process the queue
        await asyncio.sleep(0.15)
        await pool.stop()

        # Both QUIZ_1 and FLASHCARDS should be processed even though AUDIO threw QuotaExceededError
        self.assertIn(ArtifactType.QUIZ_1.value, executed_jobs)
        self.assertIn(ArtifactType.FLASHCARDS.value, executed_jobs)

        with self.session_factory() as session:
            repo = QueueRepository(session)
            audio_job = repo.get_job("j-2")
            assert audio_job is not None
            # AUDIO should either be in QUOTA_WAIT or awakened back to PENDING by the probe
            self.assertIn(audio_job.status, (JobStatus.QUOTA_WAIT, JobStatus.PENDING))

    def test_naming_prefixes_and_english_titles(self) -> None:
        """Verify Ch vs L prefix inference, range prefix calculation, and English standard titles."""
        # Ch vs L inference
        self.assertEqual(get_lecture_prefix("Ch01-Introduction.pdf", 1), "Ch01")
        self.assertEqual(get_lecture_prefix("Chapter 4.pdf", 4), "Ch04")
        self.assertEqual(get_lecture_prefix("Lecture 02 - Enzymes.pdf", 2), "L02")
        self.assertEqual(get_lecture_prefix("03_Membranes.pdf", 3), "L03")

        # Range prefix calculation
        lectures_ch = [
            Lecture(no=1, topic="Intro", filename="Ch01-Intro.pdf", sha256="h1"),
            Lecture(no=6, topic="Validity", filename="Ch06-Validity.pdf", sha256="h6"),
        ]
        self.assertEqual(get_course_range_prefix(lectures_ch), "Ch01-Ch06")

        lectures_l = [
            Lecture(no=1, topic="L1", filename="Lecture 01.pdf", sha256="h1"),
            Lecture(no=5, topic="L5", filename="Lecture 05.pdf", sha256="h5"),
        ]
        self.assertEqual(get_course_range_prefix(lectures_l), "L01-L05")

        # English title generation for NotebookLM in-app display
        self.assertEqual(
            get_artifact_english_title(ArtifactType.QUIZ_1, "Ch01"),
            "[Ch01] Quiz 1 - Fundamentals",
        )
        self.assertEqual(
            get_artifact_english_title(ArtifactType.AUDIO, "L02"),
            "[L02] Audio Overview",
        )
        self.assertEqual(
            get_artifact_english_title(ArtifactType.COURSE_MOCK_EXAM, "Ch01-Ch06"),
            "[Ch01-Ch06] Comprehensive Mock Exam",
        )
        self.assertEqual(
            get_artifact_english_title(ArtifactType.COURSE_MIND_MAP, "L01-L05"),
            "[L01-L05] Course Mind Map",
        )

    def test_granular_checkbox_job_generation(self) -> None:
        """Verify custom granular selections generate precise chapter and course-wide jobs."""
        course = Course(
            code="115-1",
            name="心理學研究法",
            source_dir="/mock/dir",
            selected_chapter_artifacts=["quiz_1", "flashcards"],
            selected_course_artifacts=["course_mock_exam", "course_mind_map"],
            lectures=[
                Lecture(no=1, topic="Intro", filename="Ch01.pdf", sha256="h1"),
                Lecture(no=2, topic="Methods", filename="Ch02.pdf", sha256="h2"),
                Lecture(no=3, topic="Hypothesis", filename="Ch03.pdf", sha256="h3"),
            ],
        )
        jobs = generate_jobs_for_course(course)
        # 3 lectures * 2 chapter artifacts + 2 course-wide artifacts = 8 jobs
        self.assertEqual(len(jobs), 8)
        chapter_jobs = [j for j in jobs if j.lecture_no is not None]
        course_jobs = [j for j in jobs if j.lecture_no is None]
        self.assertEqual(len(chapter_jobs), 6)
        self.assertEqual(len(course_jobs), 2)
        self.assertEqual(
            {j.artifact_type for j in course_jobs},
            {ArtifactType.COURSE_MOCK_EXAM, ArtifactType.COURSE_MIND_MAP},
        )

    async def test_worker_pool_graceful_pause_and_resume(self) -> None:
        """Verify graceful pause: running tasks complete, pending tasks freeze until resumed."""
        with self.session_factory() as session:
            repo = QueueRepository(session)
            repo.enqueue_jobs(
                [
                    ArtifactJob(
                        id="p-1", course_code="CS101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1
                    ),
                    ArtifactJob(
                        id="p-2", course_code="CS101", lecture_no=2, artifact_type=ArtifactType.QUIZ_2
                    ),
                ]
            )
            session.commit()

        executed: list[str] = []
        job_1_started = asyncio.Event()

        async def slow_executor(job: ArtifactJob) -> str:
            executed.append(job.id)
            job_1_started.set()
            await asyncio.sleep(0.05)
            return f"/mock/{job.id}.json"

        @contextmanager
        def queue_provider() -> Generator[QueueRepositoryProtocol, None, None]:
            with self.session_factory() as session:
                yield QueueRepository(session)
                session.commit()

        pool = WorkerPool(queue_provider, slow_executor, concurrency=1)
        await pool.start()
        # Wait until job 1 has started processing
        await job_1_started.wait()
        # Pause while job 1 is in-flight
        pool.pause()
        self.assertTrue(pool.is_paused)

        # Allow current job to finish
        await asyncio.sleep(0.1)

        # p-1 should have been executed, p-2 should still be pending because pool is paused
        self.assertEqual(executed, ["p-1"])
        with self.session_factory() as session:
            repo = QueueRepository(session)
            j2 = repo.get_job("p-2")
            assert j2 is not None
            self.assertEqual(j2.status, JobStatus.PENDING)

        # Now resume
        pool.resume()
        self.assertFalse(pool.is_paused)
        await asyncio.sleep(0.15)
        await pool.stop()

        # Both jobs executed
        self.assertEqual(executed, ["p-1", "p-2"])

    def test_lecture_upload_status_tracking(self) -> None:
        """Verify Lecture upload_status and error_message transitions in CourseRepository."""
        with self.session_factory() as session:
            repo = CourseRepository(session)
            course = Course(
                code="115-1",
                name="心理學研究法",
                source_dir="/mock/dir",
                lectures=[Lecture(no=1, topic="Intro", filename="Ch01.pdf", sha256="abc1")],
            )
            repo.save_course(course)

            # Initial state is pending
            loaded = repo.get_course("115-1")
            assert loaded is not None
            self.assertEqual(loaded.lectures[0].upload_status, "pending")

            # Update to uploading, parsing, ready
            repo.update_lecture_upload_status("115-1", 1, "uploading")
            loaded = repo.get_course("115-1")
            assert loaded is not None
            self.assertEqual(loaded.lectures[0].upload_status, "uploading")

            repo.update_lecture_upload_status("115-1", 1, "ready", source_id="src-mock-123")
            loaded = repo.get_course("115-1")
            assert loaded is not None
            self.assertEqual(loaded.lectures[0].upload_status, "ready")
            self.assertEqual(loaded.lectures[0].source_id, "src-mock-123")

    def test_prompt_generator_master_blueprint(self) -> None:
        """Verify Master Style Blueprint generates high-standard academic prompts."""
        gen = PromptGenerator()
        q1_prompt = gen.get_base_blueprint_prompt(
            ArtifactType.QUIZ_1, "科學研究導論", "心理學研究法", language="zh-TW"
        )
        self.assertIn("研究所/大學高年級水準", q1_prompt)
        self.assertIn("標準繁體中文 (zh-TW)", q1_prompt)
        self.assertIn("測驗 1 - 基礎記憶與核心定義", q1_prompt)

        exam_prompt = gen.get_base_blueprint_prompt(
            ArtifactType.COURSE_MOCK_EXAM, "全範圍整合", "心理學研究法", language="zh-TW"
        )
        self.assertIn("50 題", exam_prompt)
        self.assertIn("跨章節整合", exam_prompt)

        # English variant
        en_prompt = gen.get_base_blueprint_prompt(
            ArtifactType.QUIZ_2, "Research Methods", "Research Methods", language="en"
        )
        self.assertIn("strictly in formal academic English", en_prompt)

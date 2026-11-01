"""Unit tests for domain models, CourseRepository, QueueRepository, and WorkerPool."""

from __future__ import annotations

import asyncio
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.domain.exceptions import QuotaExceededError
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Choice,
    Course,
    GenerationOptions,
    JobStatus,
    Lecture,
    ProfileName,
    Question,
    Quiz,
    get_artifact_english_title,
    get_course_range_prefix,
    get_lecture_prefix,
)
from notebooklm_batch_studio.domain.repositories import QueueRepositoryProtocol
from notebooklm_batch_studio.services.converters.quiz_converter import to_interactive_html
from notebooklm_batch_studio.services.prompt_generator import PromptGenerator
from notebooklm_batch_studio.services.sync_service import (
    RemoteSyncService,
    get_extension_for_kind,
    infer_lecture_no_from_title,
    map_remote_kind_to_artifact_type,
)
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

    def test_quiz_dual_styles_and_reports_prompts(self) -> None:
        """Verify dual quiz styles (academic vs concept) and reports prompts and titles."""
        gen = PromptGenerator()
        acad_prompt = gen.get_base_blueprint_prompt(
            ArtifactType.QUIZ_ACADEMIC, "推論統計", "心理學研究法", language="zh-TW"
        )
        self.assertIn("高階學術精研測驗", acad_prompt)
        self.assertIn("30 題", acad_prompt)

        concept_prompt = gen.get_base_blueprint_prompt(
            ArtifactType.QUIZ_CONCEPT, "推論統計", "心理學研究法", language="zh-TW"
        )
        self.assertIn("核心概念刷題測驗", concept_prompt)
        self.assertIn("30 題", concept_prompt)

        report_prompt = gen.get_base_blueprint_prompt(
            ArtifactType.REPORTS_BRIEFING, "推論統計", "心理學研究法", language="zh-TW"
        )
        self.assertIn("高階研究摘要報告 (Briefing Doc)", report_prompt)

        # Titles
        self.assertEqual(
            get_artifact_english_title(ArtifactType.QUIZ_ACADEMIC, "Ch01"),
            "[Ch01] Quiz - Academic Advanced",
        )
        self.assertEqual(
            get_artifact_english_title(ArtifactType.QUIZ_CONCEPT, "Ch01"),
            "[Ch01] Quiz - Concept Drill",
        )
        self.assertEqual(
            get_artifact_english_title(ArtifactType.REPORTS_BRIEFING, "Ch01"),
            "[Ch01] Reports - Briefing Doc",
        )

    def test_to_interactive_html(self) -> None:
        """Verify self-contained interactive quiz web app generation."""
        quiz = Quiz(
            course_code="CS101",
            lecture_no=1,
            variant="學術精研",
            title="CS101 - 學術精研測驗",
            source_pdf="01.pdf",
            prompt_version="v2",
            questions=[
                Question(
                    id="Q1",
                    question="何謂第一型錯誤 (Type I Error)?",
                    choices=[
                        Choice(text="虛無假說為真卻拒絕", is_correct=True),
                        Choice(text="虛無假說為偽卻接受", is_correct=False),
                        Choice(text="對立假說為真卻拒絕", is_correct=False),
                        Choice(text="樣本數過大導致拒絕", is_correct=False),
                    ],
                    answer_index=0,
                    explanation="Type I error 即為虛報 (false positive)。",
                )
            ],
        )
        html = to_interactive_html(quiz)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("何謂第一型錯誤", html)
        self.assertIn("quiz-container", html)
        self.assertIn("submitAll()", html)
        self.assertIn("交卷評分", html)

        # Verify XSS sanitization in title and JSON data payload
        quiz_xss = Quiz(
            course_code="CS101",
            lecture_no=1,
            variant="學術精研",
            title="CS101 <script>alert(1)</script>",
            source_pdf="01.pdf",
            prompt_version="v2",
            questions=[
                Question(
                    id="Q1",
                    question="何謂 <script>alert('xss')</script>?",
                    choices=[Choice(text="<b>Bold</b>", is_correct=True)],
                    answer_index=0,
                    explanation="<img src=x onerror=alert(1)>",
                )
            ],
        )
        html_xss = to_interactive_html(quiz_xss)
        self.assertNotIn("<h1>CS101 <script>alert(1)</script></h1>", html_xss)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_xss)
        self.assertIn("\\u003cscript\\u003ealert('xss')\\u003c/script\\u003e", html_xss)

    async def test_remote_sync_helpers_and_service(self) -> None:
        """Verify remote sync inference, kind mapping, and sync execution."""
        self.assertEqual(infer_lecture_no_from_title("[Ch02] Quiz 1", 10), 2)
        self.assertEqual(infer_lecture_no_from_title("Chapter 5 - Summary", 10), 5)
        self.assertEqual(infer_lecture_no_from_title("Lecture 3 Notes", 10), 3)
        self.assertIsNone(infer_lecture_no_from_title("Course Final Mock Exam", 10))

        self.assertEqual(map_remote_kind_to_artifact_type("flashcards"), ArtifactType.FLASHCARDS)
        self.assertEqual(map_remote_kind_to_artifact_type("mind_map"), ArtifactType.MIND_MAP)
        self.assertEqual(map_remote_kind_to_artifact_type("audio"), ArtifactType.AUDIO)
        self.assertEqual(map_remote_kind_to_artifact_type("briefing_doc"), ArtifactType.REPORTS_BRIEFING)
        # Refs: ISSUE-007 — NotebookLM audio is MP4/AAC and infographics are PNG.
        self.assertEqual(get_extension_for_kind("audio"), ".m4a")
        self.assertEqual(get_extension_for_kind("infographic"), ".png")

        import tempfile
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.session_factory() as session:
                course_repo = CourseRepository(session)
                queue_repo = QueueRepository(session)
                course = Course(
                    code="PSY200",
                    name="心理測驗學",
                    source_dir="/mock/dir",
                    notebook_id="nb-psy-200",
                    lectures=[Lecture(no=1, topic="Intro", filename="Ch01.pdf", sha256="abc1")],
                )
                course_repo.save_course(course)

                mock_client = MagicMock()
                mock_client.list_artifacts = AsyncMock(
                    return_value=[
                        {
                            "id": "art-1",
                            "title": "[Ch01] Manual Web Quiz",
                            "kind": "quiz",
                            "is_completed": True,
                        },
                        {
                            "id": "art-2",
                            "title": "Course Wide Summary",
                            "kind": "briefing_doc",
                            "is_completed": True,
                        },
                    ]
                )
                mock_client.download_artifact_by_kind = AsyncMock(
                    side_effect=lambda notebook_id, artifact_id, kind, output_path: output_path
                )

                sync_svc = RemoteSyncService(
                    notebooklm_client=mock_client,
                    course_repo=course_repo,
                    queue_repo=queue_repo,
                    output_base_dir=Path(tmp_dir),
                )
                res = await sync_svc.sync_course("PSY200")
                self.assertEqual(res["synced_count"], 2)
                self.assertEqual(len(res["items"]), 2)

                # Verify database records
                jobs = queue_repo.list_jobs(course_code="PSY200")
                self.assertEqual(len(jobs), 2)
                self.assertTrue(all(j.source_origin == "remote_sync" for j in jobs))
                self.assertTrue(res["items"][0]["path"].endswith("01_Intro/[Ch01] Manual Web Quiz.json"))
                self.assertTrue(res["items"][1]["path"].endswith("manual_artifacts/Course Wide Summary.html"))

                # Test deduplication on second run
                res_repeat = await sync_svc.sync_course("PSY200")
                self.assertEqual(res_repeat["synced_count"], 0)

    async def test_quiz_variants_preserve_separate_files_and_use_prompt(self) -> None:
        """Verify quiz variants write separate files and use job.custom_prompt."""
        import json
        import tempfile
        from unittest.mock import AsyncMock, MagicMock

        from notebooklm_batch_studio.services.artifact_runner import ArtifactRunner

        mock_client = MagicMock()
        mock_client.generate_quiz = AsyncMock(return_value="task-quiz-1")
        mock_client.generate_audio = AsyncMock(return_value="task-audio-1")
        mock_client.generate_flashcards = AsyncMock(return_value="task-fc-1")
        mock_client.generate_mind_map = AsyncMock(return_value="task-mm-1")
        mock_client.rename_artifact = AsyncMock()

        sample_quiz_payload = {
            "questions": [
                {
                    "question": f"Sample Question {i}?",
                    "choices": ["A", "B", "C", "D"],
                    "answer_index": 0,
                    "explanation": "Sample Explanation",
                }
                for i in range(30)
            ]
        }

        async def fake_download_quiz(notebook_id: str, path: str, artifact_id: str | None = None) -> None:
            Path(path).write_text(json.dumps(sample_quiz_payload), encoding="utf-8")

        async def fake_download_audio(notebook_id: str, path: str, artifact_id: str | None = None) -> None:
            Path(path).write_bytes(b"MP3")

        async def fake_download_fc(notebook_id: str, path: str, artifact_id: str | None = None) -> None:
            Path(path).write_text(json.dumps({"cards": [{"front": "Q", "back": "A"}]}), encoding="utf-8")

        async def fake_download_mm(notebook_id: str, path: str, artifact_id: str | None = None) -> None:
            Path(path).write_text(json.dumps({"root": "Topic"}), encoding="utf-8")

        mock_client.download_quiz = AsyncMock(side_effect=fake_download_quiz)
        mock_client.download_audio = AsyncMock(side_effect=fake_download_audio)
        mock_client.download_flashcards = AsyncMock(side_effect=fake_download_fc)
        mock_client.download_mind_map = AsyncMock(side_effect=fake_download_mm)

        runner = ArtifactRunner(mock_client)
        course = Course(
            code="BIO101",
            name="General Biology",
            source_dir="/mock",
            notebook_id="nb-1",
            language="zh-TW",
            lectures=[Lecture(no=1, topic="Membranes", filename="01.pdf", sha256="h1")],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "01_Membranes"
            out_dir.mkdir(parents=True)

            # 1. Run Academic Quiz
            job_acad = ArtifactJob(
                id="job-acad",
                course_code="BIO101",
                lecture_no=1,
                artifact_type=ArtifactType.QUIZ_ACADEMIC,
                custom_prompt="Custom Academic Blueprint Prompt 123",
            )
            res_acad = await runner.process_job(job_acad, course, "nb-1", ["src-1"], out_dir)

            # Check prompt was passed to generate_quiz
            mock_client.generate_quiz.assert_called_with(
                "nb-1",
                ["src-1"],
                prompt="Custom Academic Blueprint Prompt 123",
                difficulty="hard",
                options=GenerationOptions(),
            )

            # 2. Run Concept Quiz on the same directory
            job_conc = ArtifactJob(
                id="job-conc",
                course_code="BIO101",
                lecture_no=1,
                artifact_type=ArtifactType.QUIZ_CONCEPT,
                custom_prompt="Custom Concept Drill Prompt 456",
            )
            res_conc = await runner.process_job(job_conc, course, "nb-1", ["src-1"], out_dir)

            # Check prompt was passed to generate_quiz
            mock_client.generate_quiz.assert_called_with(
                "nb-1",
                ["src-1"],
                prompt="Custom Concept Drill Prompt 456",
                difficulty="medium",
                options=GenerationOptions(),
            )

            # Crucial check: both files must coexist and not overwrite each other!
            self.assertNotEqual(res_acad, res_conc)
            self.assertTrue(Path(res_acad).exists())
            self.assertTrue(Path(res_conc).exists())

            # 3. Check Audio, Flashcards, Mind Map custom prompt forwarding
            job_audio = ArtifactJob(
                id="job-audio",
                course_code="BIO101",
                lecture_no=1,
                artifact_type=ArtifactType.AUDIO,
                custom_prompt="Custom Audio Prompt 789",
            )
            await runner.process_job(job_audio, course, "nb-1", ["src-1"], out_dir)
            mock_client.generate_audio.assert_called_with(
                "nb-1",
                ["src-1"],
                prompt="Custom Audio Prompt 789",
                language="zh-TW",
                options=GenerationOptions(),
            )

            job_fc = ArtifactJob(
                id="job-fc",
                course_code="BIO101",
                lecture_no=1,
                artifact_type=ArtifactType.FLASHCARDS,
                custom_prompt="Custom Flashcards Prompt 999",
            )
            await runner.process_job(job_fc, course, "nb-1", ["src-1"], out_dir)
            mock_client.generate_flashcards.assert_called_with(
                "nb-1", ["src-1"], prompt="Custom Flashcards Prompt 999", options=GenerationOptions()
            )

            job_mm = ArtifactJob(
                id="job-mm",
                course_code="BIO101",
                lecture_no=1,
                artifact_type=ArtifactType.MIND_MAP,
                custom_prompt="Custom MindMap Prompt 888",
            )
            await runner.process_job(job_mm, course, "nb-1", ["src-1"], out_dir)
            mock_client.generate_mind_map.assert_called_with(
                "nb-1", ["src-1"], prompt="Custom MindMap Prompt 888", language="zh-TW"
            )

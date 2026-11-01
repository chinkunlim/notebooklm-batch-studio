"""Regression tests for TASK-007: needs_review job status and Ollama prompt refinement wiring.

Covers two bugs: incomplete quizzes were marked DONE instead of NEEDS_REVIEW, and
`refine_course_prompts_with_ollama` never called Ollama because no client was injected.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import NeedsReviewError, OllamaUnavailableError
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course, JobStatus, Lecture
from notebooklm_batch_studio.domain.repositories import QueueRepositoryProtocol
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.worker_pool import WorkerPool

REFINED_TEXT = (
    "請以研究所程度為【細胞膜】出 10 題情境應用選擇題，每題附四個選項、正確答案、"
    "逐項錯誤選項解析與講義出處頁碼，並以繁體中文輸出。"
)


class FakeOllamaClient:
    """Offline stand-in for OllamaClientProtocol."""

    def __init__(self, available: bool = True) -> None:
        """Initialize the fake client.

        Args:
            available: Value returned by is_available().
        """
        self.available = available
        self.calls: list[str] = []

    def is_available(self) -> bool:
        """Report the configured availability.

        Returns:
            The `available` flag.
        """
        return self.available

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Record the call and return a fixed refined prompt.

        Args:
            prompt: User prompt content.
            system_prompt: Optional system prompt context.

        Returns:
            A fixed refined prompt string.
        """
        self.calls.append(prompt)
        return REFINED_TEXT


class NeedsReviewTest(unittest.IsolatedAsyncioTestCase):
    """Incomplete artifacts must land in NEEDS_REVIEW, not DONE."""

    def setUp(self) -> None:
        """Create an in-memory database with one pending quiz job."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as session:
            QueueRepository(session).enqueue_jobs(
                [ArtifactJob(id="q-1", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1)]
            )
            session.commit()

    @contextmanager
    def _provider(self) -> Iterator[QueueRepositoryProtocol]:
        """Yield a queue repository bound to a fresh session.

        Yields:
            QueueRepository instance.
        """
        with self.session_factory() as session:
            yield QueueRepository(session)
            session.commit()

    async def test_worker_marks_job_needs_review(self) -> None:
        """A NeedsReviewError from the executor sets NEEDS_REVIEW and keeps the output path."""
        calls: list[str] = []

        async def executor(job: ArtifactJob) -> str:
            calls.append(job.id)
            raise NeedsReviewError("only 10 of 30 questions", output_file="/data/needs_review/q.json")

        pool = WorkerPool(self._provider, executor, concurrency=1)
        await pool.start()
        await asyncio.sleep(0.2)
        await pool.stop()

        with self.session_factory() as session:
            job = QueueRepository(session).get_job("q-1")
        assert job is not None
        self.assertEqual(job.status, JobStatus.NEEDS_REVIEW)
        self.assertEqual(job.output_file, "/data/needs_review/q.json")
        self.assertEqual(calls, ["q-1"], "needs_review jobs must not be retried automatically")

    def test_retry_resets_needs_review_job(self) -> None:
        """retry_job moves a NEEDS_REVIEW job back to PENDING."""
        with self.session_factory() as session:
            repo = QueueRepository(session)
            repo.mark_needs_review("q-1", output_file="/x.json", message="short")
            self.assertTrue(repo.retry_job("q-1"))
            job = repo.get_job("q-1")
        assert job is not None
        self.assertEqual(job.status, JobStatus.PENDING)


class OllamaRefineTest(unittest.TestCase):
    """refine_course_prompts_with_ollama must actually use the injected Ollama client."""

    def setUp(self) -> None:
        """Create a course with one pending and one finished job."""
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.config = AppConfig(data_dir=tmp / "data", notebooklm_home=tmp / "cfg", log_to_file=False)
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.course_repo = CourseRepository(self.session)
        self.queue_repo = QueueRepository(self.session)
        self.course_repo.save_course(
            Course(
                code="BIO101",
                name="細胞生物學",
                source_dir=str(tmp),
                lectures=[Lecture(no=1, topic="細胞膜", filename="01_細胞膜.pdf", sha256="a")],
            )
        )
        self.queue_repo.enqueue_jobs(
            [
                ArtifactJob(
                    id="p-1",
                    course_code="BIO101",
                    lecture_no=1,
                    artifact_type=ArtifactType.QUIZ_1,
                    custom_prompt="base",
                ),
                ArtifactJob(
                    id="d-1",
                    course_code="BIO101",
                    lecture_no=1,
                    artifact_type=ArtifactType.AUDIO,
                    custom_prompt="base",
                ),
            ]
        )
        self.queue_repo.complete_job("d-1", "/out/audio.mp3")

    def tearDown(self) -> None:
        """Close the session and remove temporary files."""
        self.session.close()
        self.tmpdir.cleanup()

    def _service(self, ollama: FakeOllamaClient | None) -> BatchStudioService:
        """Build the service under test.

        Args:
            ollama: Optional fake Ollama client to inject.

        Returns:
            BatchStudioService instance.
        """
        return BatchStudioService(
            self.course_repo,
            self.queue_repo,
            notebooklm_client=None,  # type: ignore[arg-type]
            config=self.config,
            ollama_client=ollama,
        )

    def test_refine_updates_unfinished_jobs_with_ollama_output(self) -> None:
        """Pending jobs get the Ollama text; finished jobs are left alone."""
        fake = FakeOllamaClient()
        count = self._service(fake).refine_course_prompts_with_ollama("BIO101")

        self.assertEqual(count, 1)
        self.assertEqual(len(fake.calls), 1)
        pending = self.queue_repo.get_job("p-1")
        done = self.queue_repo.get_job("d-1")
        assert pending is not None and done is not None
        self.assertEqual(pending.custom_prompt, REFINED_TEXT)
        self.assertEqual(done.custom_prompt, "base")

    def test_refine_raises_when_ollama_missing_or_down(self) -> None:
        """No client or an unreachable Ollama raises instead of reporting fake success."""
        with self.assertRaises(OllamaUnavailableError):
            self._service(None).refine_course_prompts_with_ollama("BIO101")
        with self.assertRaises(OllamaUnavailableError):
            self._service(FakeOllamaClient(available=False)).refine_course_prompts_with_ollama("BIO101")


if __name__ == "__main__":
    unittest.main()

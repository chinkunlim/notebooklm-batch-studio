"""Regression tests for ISSUE-038: failed job manual rerun and automatic retry recovery."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.models import ArtifactJobRecord, utc_now
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course, JobStatus, Lecture
from notebooklm_batch_studio.domain.repositories import QueueRepositoryProtocol
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.quiz_runner import JobTarget, QuizRunner
from notebooklm_batch_studio.services.worker_pool import WorkerPool


def _seed_course(session: object, code: str = "BIO101", tmp: str = "/mock") -> None:
    """Persist a sample single-lecture course into the test DB session.

    Args:
        session: SQLAlchemy session.
        code: Course code to create.
        tmp: Mock source directory path.
    """
    CourseRepository(session).save_course(  # type: ignore[arg-type]
        Course(
            code=code,
            name="Cell Biology",
            source_dir=tmp,
            lectures=[Lecture(no=1, topic="Cell", filename="01_cell.pdf", sha256="abc")],
        )
    )


class FailedJobRetryAndRecoveryTest(unittest.IsolatedAsyncioTestCase):
    """Verify retry_job attempt reset, auto-retry rounds, probe recovery, and orphan recovery."""

    def setUp(self) -> None:
        """Create shared file-backed SQLite DB in a temporary folder."""
        self.tmpdir = tempfile.TemporaryDirectory()
        db_file = Path(self.tmpdir.name) / "test.db"
        self.engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as session:
            _seed_course(session, tmp=self.tmpdir.name)
            session.commit()

    def tearDown(self) -> None:
        """Dispose database engine and clean temporary directory."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    @contextmanager
    def _provider(self) -> Iterator[QueueRepositoryProtocol]:
        """Yield a short-lived QueueRepository for WorkerPool workers.

        Yields:
            Bound QueueRepositoryProtocol instance.
        """
        with self.session_factory() as session:
            yield QueueRepository(session)

    def test_retry_job_resets_attempts_and_cooldown(self) -> None:
        """Exhausting 3 attempts marks FAILED with cooldown; retry_job resets attempts=0."""
        with self.session_factory() as session:
            repo = QueueRepository(session)
            repo.enqueue_jobs(
                [ArtifactJob(id="j1", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.AUDIO)]
            )
            for idx in range(3):
                claimed = repo.claim_next_job("w1")
                self.assertIsNotNone(claimed)
                repo.fail_job("j1", f"boom-{idx + 1}", max_attempts=3)

            failed = repo.get_job("j1")
            assert failed is not None
            self.assertEqual(failed.status, JobStatus.FAILED)
            self.assertEqual(failed.attempts, 3)
            self.assertIsNotNone(failed.cooldown_until)

            self.assertTrue(repo.retry_job("j1"))
            retried = repo.get_job("j1")
            assert retried is not None
            self.assertEqual(retried.status, JobStatus.PENDING)
            self.assertEqual(retried.attempts, 0)
            self.assertIsNone(retried.error_message)
            self.assertIsNone(retried.cooldown_until)

    async def test_worker_pool_auto_retries_and_recovers_failed_and_orphans(self) -> None:
        """WorkerPool retries transient failures, recovers expired FAILED jobs, and resets RUNNING."""
        with self.session_factory() as session:
            repo = QueueRepository(session)
            repo.enqueue_jobs(
                [
                    ArtifactJob(
                        id="j-trans", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.AUDIO
                    ),
                    ArtifactJob(
                        id="j-cool", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1
                    ),
                    ArtifactJob(
                        id="j-orphan",
                        course_code="BIO101",
                        lecture_no=1,
                        artifact_type=ArtifactType.MIND_MAP,
                    ),
                    ArtifactJob(
                        id="j-cap",
                        course_code="BIO101",
                        lecture_no=1,
                        artifact_type=ArtifactType.FLASHCARDS,
                    ),
                ]
            )
            past = utc_now() - timedelta(seconds=5)
            cool_row = session.get(ArtifactJobRecord, "j-cool")
            assert cool_row is not None
            cool_row.status = JobStatus.FAILED.value
            cool_row.attempts = 3
            cool_row.cooldown_until = past

            orphan_row = session.get(ArtifactJobRecord, "j-orphan")
            assert orphan_row is not None
            orphan_row.status = JobStatus.RUNNING.value
            orphan_row.attempts = 1

            cap_row = session.get(ArtifactJobRecord, "j-cap")
            assert cap_row is not None
            cap_row.status = JobStatus.FAILED.value
            cap_row.attempts = 9
            cap_row.cooldown_until = past
            session.commit()

        seen_calls: dict[str, int] = {}

        async def executor(job: ArtifactJob) -> str:
            seen_calls[job.id] = seen_calls.get(job.id, 0) + 1
            if job.id == "j-trans" and seen_calls[job.id] < 3:
                raise RuntimeError("transient network hiccup")
            return f"/out/{job.id}.dat"

        pool = WorkerPool(self._provider, executor, concurrency=2, probe_interval_seconds=0.05)
        await pool.start()
        await asyncio.sleep(0.8)
        await pool.stop()

        with self.session_factory() as session:
            repo = QueueRepository(session)
            for jid in ("j-trans", "j-cool", "j-orphan"):
                item = repo.get_job(jid)
                assert item is not None
                self.assertEqual(item.status, JobStatus.DONE, f"{jid} should finish DONE")
            capped = repo.get_job("j-cap")
            assert capped is not None
            self.assertEqual(capped.status, JobStatus.FAILED, "9-attempt FAILED job stops auto-retrying")
            # Manual course-wide retry resets attempts=0 even after auto cap.
            self.assertEqual(repo.retry_failed_jobs(course_code="BIO101", respect_cooldown=False), 1)
            capped_after = repo.get_job("j-cap")
            assert capped_after is not None
            self.assertEqual(capped_after.attempts, 0)
            self.assertEqual(capped_after.status, JobStatus.PENDING)

    async def test_quiz_runner_survives_transient_batch_failure(self) -> None:
        """One failing batch attempt does not abort remaining quiz generation attempts."""
        attempts = {"count": 0}

        class PartialFailureClient:
            """Fake client failing on the first quiz batch then returning 15 questions per call."""

            async def generate_quiz(self, *_args: object, **_kwargs: object) -> str:
                attempts["count"] += 1
                if attempts["count"] == 1:
                    raise RuntimeError("temporary backend timeout")
                return f"quiz-{attempts['count']}"

            async def download_quiz(self, _nb: str, out_path: str, artifact_id: str | None = None) -> None:
                start = 0 if artifact_id == "quiz-2" else 15
                qs = [
                    {
                        "question": f"Q{i}?",
                        "choices": ["A", "B", "C", "D"],
                        "answer_index": 0,
                        "explanation": "Exp",
                    }
                    for i in range(start, start + 15)
                ]
                Path(out_path).write_text(json.dumps({"questions": qs}), encoding="utf-8")

        runner = QuizRunner(
            PartialFailureClient(),  # type: ignore[arg-type]
            Path(self.tmpdir.name) / "review",
            lambda *_args: asyncio.sleep(0),
        )
        course = Course(
            code="BIO101",
            name="Bio",
            source_dir=self.tmpdir.name,
            lectures=[Lecture(no=1, topic="Cell", filename="01.pdf", sha256="h")],
        )
        job = ArtifactJob(id="qz-1", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1)
        out_dir = Path(self.tmpdir.name) / "out"
        out_dir.mkdir()
        out_path, ids = await runner.process_quiz(job, course, JobTarget("nb-1", ["s1"], out_dir))
        self.assertTrue(Path(out_path).exists())
        self.assertEqual(ids, ["quiz-2", "quiz-3"])


class FailedJobHttpAndMcpTest(unittest.TestCase):
    """Verify HTTP and MCP bulk/single retry endpoints start the queue cleanly."""

    def setUp(self) -> None:
        """Set up in-memory DB, service, TestClient, and MCP server."""
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.config = AppConfig(
            data_dir=tmp / "data",
            notebooklm_home=tmp / "cfg",
            log_to_file=False,
            http_allowed_hosts=("testserver",),
        )
        self.engine = create_db_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = session_scope(self.engine).__enter__()
        _seed_course(self.session, tmp=self.tmpdir.name)
        self.queue_repo = QueueRepository(self.session)
        self.queue_repo.enqueue_jobs(
            [
                ArtifactJob(
                    id="j-fail", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.AUDIO
                ),
                ArtifactJob(
                    id="j-rev", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1
                ),
                ArtifactJob(
                    id="j-done", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.MIND_MAP
                ),
            ]
        )
        self.queue_repo.mark_needs_review("j-rev", "/review/q.json", "short")
        self.queue_repo.complete_job("j-done", "/out/mm.opml")
        for _ in range(3):
            claimed = self.queue_repo.claim_next_job("w1")
            assert claimed is not None and claimed.id == "j-fail"
            self.queue_repo.fail_job("j-fail", "err", max_attempts=3)

        self.service = BatchStudioService(
            CourseRepository(self.session), self.queue_repo, mock.MagicMock(), self.config
        )
        self.http = TestClient(
            create_app(config=self.config, service=self.service, study_service=mock.MagicMock())
        )

    def tearDown(self) -> None:
        """Close DB session, dispose engine, and remove temp directory."""
        self.session.close()
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_http_and_mcp_retry_failed_endpoints(self) -> None:
        """POST /retry and /retry-failed reset statuses, keep DONE untouched, and call start_queue."""
        with mock.patch.object(self.service, "start_queue") as start_spy:
            res = self.http.post("/api/courses/BIO101/jobs/retry-failed")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json(), {"course_code": "BIO101", "retried_count": 2})
            start_spy.assert_called_once()

        self.assertEqual(self.queue_repo.get_job("j-fail").status, JobStatus.PENDING)  # type: ignore[union-attr]
        self.assertEqual(self.queue_repo.get_job("j-rev").status, JobStatus.PENDING)  # type: ignore[union-attr]
        self.assertEqual(self.queue_repo.get_job("j-done").status, JobStatus.DONE)  # type: ignore[union-attr]
        self.assertEqual(self.http.post("/api/courses/NOPE/jobs/retry-failed").status_code, 404)

        # Complete j-rev so claim_next_job targets j-fail reliably, then re-fail j-fail.
        self.queue_repo.complete_job("j-rev", "/out/q.json")
        for _ in range(3):
            claimed = self.queue_repo.claim_next_job("w1")
            assert claimed is not None and claimed.id == "j-fail"
            self.queue_repo.fail_job("j-fail", "err", max_attempts=3)
        self.assertEqual(self.queue_repo.get_job("j-fail").status, JobStatus.FAILED)  # type: ignore[union-attr]
        with mock.patch.object(self.service, "start_queue") as single_spy:
            self.assertEqual(self.http.post("/api/jobs/j-fail/retry").status_code, 200)
            single_spy.assert_called_once()
        self.assertEqual(self.queue_repo.get_job("j-fail").status, JobStatus.PENDING)  # type: ignore[union-attr]

        for _ in range(3):
            claimed = self.queue_repo.claim_next_job("w1")
            assert claimed is not None and claimed.id == "j-fail"
            self.queue_repo.fail_job("j-fail", "err", max_attempts=3)
        mcp = build_mcp_server(service=self.service, study_service=mock.MagicMock(), config=self.config)
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        unconfirmed = json.loads(tools["retry_course_failed_jobs"].fn("BIO101"))
        self.assertFalse(unconfirmed["confirmed"])
        self.assertIn("warning", unconfirmed)
        with mock.patch.object(self.service, "start_queue"):
            confirmed = json.loads(tools["retry_course_failed_jobs"].fn("BIO101", confirm=True))
        self.assertTrue(confirmed["confirmed"])
        self.assertEqual(confirmed["retried_count"], 1)

"""Regression tests for ISSUE-008..010: quota pre-check, mock-exam quarantine, review downloads."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import NeedsReviewError, QuotaExceededError
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course, JobStatus, Lecture
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.services.artifact_runner import ArtifactRunner
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.quota_planner import (
    action_kind_for,
    estimate_quota_plan,
    quota_retry_after,
)
from tests.test_notebooklm_generation import RecordingProtocolClient

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def make_quota(audio_ok: bool = True, five_hour_remaining: float = 50.0) -> dict[str, Any]:
    """Build a quota summary shaped like NotebookLMAdapter.get_quota_status().

    Args:
        audio_ok: Whether audio has sufficient quota.
        five_hour_remaining: Remaining percent of the five-hour window.

    Returns:
        Quota dictionary.
    """
    return {
        "status": "ready",
        "windows": [
            {
                "kind": "five_hour",
                "remaining_percent": five_hour_remaining,
                "resets_at": (NOW + timedelta(hours=2)).isoformat(),
            },
            {"kind": "weekly", "remaining_percent": 90.0, "resets_at": (NOW + timedelta(days=3)).isoformat()},
        ],
        "actions": [
            {"kind": "audio_overview", "has_sufficient_quota": audio_ok, "estimated_cost_percent": 10.0},
            {"kind": "quiz", "has_sufficient_quota": True, "estimated_cost_percent": 0.5},
            {"kind": "reports", "has_sufficient_quota": True, "estimated_cost_percent": 1.5},
        ],
    }


class QuotaPlannerTest(unittest.TestCase):
    """Pure quota helpers."""

    def test_action_kind_mapping(self) -> None:
        """Lecture and course types map to the meter's action kinds."""
        self.assertEqual(action_kind_for(ArtifactType.COURSE_AUDIO), "audio_overview")
        self.assertEqual(action_kind_for(ArtifactType.COURSE_MOCK_EXAM), "quiz")
        self.assertEqual(action_kind_for(ArtifactType.QUIZ_ACADEMIC), "quiz")
        self.assertEqual(action_kind_for(ArtifactType.STUDY_GUIDE), "reports")
        self.assertEqual(action_kind_for(ArtifactType.SLIDE_DECK), "slides")

    def test_retry_after_only_when_insufficient(self) -> None:
        """Insufficient audio waits until the blocking window resets; sufficient types do not wait."""
        self.assertIsNone(quota_retry_after(make_quota(), ArtifactType.AUDIO, NOW))
        wait = quota_retry_after(make_quota(audio_ok=False, five_hour_remaining=5.0), ArtifactType.AUDIO, NOW)
        self.assertEqual(wait, 2 * 3600)
        self.assertIsNone(quota_retry_after({"status": "disabled"}, ArtifactType.AUDIO, NOW))

    def test_estimate_uses_live_costs(self) -> None:
        """Six audio jobs cost 60% of a window; with 50% left the wait is until the reset (2 h)."""
        plan = estimate_quota_plan([ArtifactType.AUDIO] * 6, make_quota(five_hour_remaining=50.0), now=NOW)
        self.assertEqual(plan["estimated_quota_percent"], 60.0)
        self.assertEqual(plan["estimated_windows"], 2)
        self.assertEqual(plan["estimated_wait_hours"], 2.0)  # until the current window resets
        self.assertEqual(plan["estimated_days"], 1)
        self.assertFalse(estimate_quota_plan([ArtifactType.AUDIO], None)["quota_estimate_available"])


class ServiceFixture(unittest.IsolatedAsyncioTestCase):
    """Shared in-memory DB, config and one uploaded two-lecture course."""

    def setUp(self) -> None:
        """Create database, config and course."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        for name in ("01_a.pdf", "02_b.pdf"):
            (self.tmp / name).write_bytes(b"%PDF-1.4 " + name.encode())
        self.config = AppConfig(
            data_dir=self.tmp / "data",
            notebooklm_home=self.tmp / "cfg",
            log_to_file=False,
            http_allowed_hosts=("testserver",),
        )
        self.engine = create_db_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = session_scope(self.engine).__enter__()
        self.course_repo = CourseRepository(self.session)
        self.queue_repo = QueueRepository(self.session)
        self.course_repo.save_course(
            Course(
                code="BIO101",
                name="細胞生物學",
                source_dir=str(self.tmp),
                notebook_id="nb",
                lectures=[
                    Lecture(no=1, topic="a", filename="01_a.pdf", sha256="a", source_id="s1"),
                    Lecture(no=2, topic="b", filename="02_b.pdf", sha256="b", source_id="s2"),
                ],
            )
        )

    def tearDown(self) -> None:
        """Close the session and remove temporary files."""
        self.session.close()
        self.tmpdir.cleanup()

    def service(self, client: Any) -> BatchStudioService:
        """Build the service under test.

        Args:
            client: Fake Gemini Notebook client.

        Returns:
            BatchStudioService.
        """
        return BatchStudioService(self.course_repo, self.queue_repo, client, self.config)


class QuotaPrecheckTest(ServiceFixture):
    """execute_job checks the live meter before spending a request."""

    async def test_insufficient_quota_raises_before_generation(self) -> None:
        """Audio with no quota raises QuotaExceededError and never calls generate_audio."""
        client = RecordingProtocolClient()
        client.get_quota_status = mock.AsyncMock(  # type: ignore[method-assign]
            return_value=make_quota(audio_ok=False, five_hour_remaining=5.0)
        )
        job = ArtifactJob(id="j1", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.AUDIO)
        with self.assertRaises(QuotaExceededError) as ctx:
            await self.service(client).execute_job(job)
        self.assertGreaterEqual(ctx.exception.retry_after_seconds, 60)
        self.assertEqual(client.called("generate_audio"), [])

    async def test_meter_error_does_not_block_generation(self) -> None:
        """If the meter cannot be read, the job still runs (fail open)."""
        client = RecordingProtocolClient()
        client.get_quota_status = mock.AsyncMock(side_effect=RuntimeError("meter down"))  # type: ignore[method-assign]
        job = ArtifactJob(id="j2", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.AUDIO)
        await self.service(client).execute_job(job)
        self.assertEqual(len(client.called("generate_audio")), 1)

    def test_quota_wait_does_not_consume_an_attempt(self) -> None:
        """A quota block gives the claimed attempt back, so waits never exhaust retries."""
        job = ArtifactJob(id="j3", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.AUDIO)
        self.queue_repo.enqueue_jobs([job])
        claimed = self.queue_repo.claim_next_job(worker_id="w")
        assert claimed is not None
        self.queue_repo.block_job_quota("j3", ArtifactType.AUDIO, cooldown_seconds=60)
        stored = self.queue_repo.get_job("j3")
        assert stored is not None
        self.assertEqual(stored.status, JobStatus.QUOTA_WAIT)
        self.assertEqual(stored.attempts, 0)


class PreviewEstimateTest(ServiceFixture):
    """Course preview counts the real profile jobs and uses live quota costs."""

    async def test_preview_counts_profile_jobs_and_quota(self) -> None:
        """Full profile: 8 jobs per lecture + 2 course jobs, with a live quota estimate."""
        client = mock.MagicMock()
        client.get_quota_status = mock.AsyncMock(return_value=make_quota())
        result = (await self.service(client).preview_course_folders([str(self.tmp)]))[0]
        self.assertTrue(result["is_valid"], result)
        self.assertEqual(result["estimated_jobs"], 2 * 8 + 2)
        self.assertTrue(result["quota_estimate_available"])
        self.assertGreater(result["estimated_quota_percent"], 0)


class MockExamQuarantineTest(unittest.IsolatedAsyncioTestCase):
    """An incomplete course mock exam goes to needs_review/ like lecture quizzes."""

    async def test_incomplete_mock_exam_raises_needs_review(self) -> None:
        """Empty quiz batches yield NeedsReviewError with a file under needs_review/."""
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            cfg = AppConfig(data_dir=tmp / "data", notebooklm_home=tmp / "cfg", log_to_file=False)
            client = RecordingProtocolClient()
            runner = ArtifactRunner(client, cfg)  # type: ignore[arg-type]
            course = Course(code="BIO101", name="x", source_dir=str(tmp), lectures=[])
            job = ArtifactJob(
                id="m", course_code="BIO101", lecture_no=None, artifact_type=ArtifactType.COURSE_MOCK_EXAM
            )
            out_dir = tmp / "out"
            with self.assertRaises(NeedsReviewError) as ctx:
                await runner.process_job(job, course, "nb", ["s1"], out_dir)
            review = Path(ctx.exception.output_file)
            self.assertTrue(review.is_file())
            self.assertTrue(review.is_relative_to(cfg.needs_review_dir))
            self.assertFalse((out_dir / "course_mock_exam_quiz.json").exists())


class ReviewDownloadTest(ServiceFixture):
    """Quarantined files are listed with a `_needs_review/` path and can be downloaded."""

    def test_needs_review_file_is_downloadable(self) -> None:
        """rel_path points at `_needs_review/...`, the route serves it, and other courses are refused."""
        review = self.config.needs_review_dir / "BIO101_L1_quiz_1" / "quiz_1_quiz.json"
        review.parent.mkdir(parents=True)
        review.write_text('{"questions": []}', encoding="utf-8")
        other = self.config.needs_review_dir / "CS101_L1_quiz_1" / "quiz_1_quiz.json"
        other.parent.mkdir(parents=True)
        other.write_text("{}", encoding="utf-8")
        job = ArtifactJob(id="r1", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_1)
        self.queue_repo.enqueue_jobs([job])
        self.queue_repo.mark_needs_review("r1", str(review), "Quiz has 12/30 questions")

        service = self.service(mock.MagicMock())
        detail = service.get_course_detail("BIO101")
        rel = next(j["rel_path"] for j in detail["jobs"] if j["id"] == "r1")
        self.assertEqual(rel, "_needs_review/BIO101_L1_quiz_1/quiz_1_quiz.json")

        app = create_app(config=self.config, service=service, study_service=mock.MagicMock())
        http = TestClient(app)
        resp = http.get(f"/api/artifacts/BIO101/download/{rel}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"questions": []})
        denied = http.get("/api/artifacts/BIO101/download/_needs_review/CS101_L1_quiz_1/quiz_1_quiz.json")
        self.assertIn(denied.status_code, (403, 404))


if __name__ == "__main__":
    unittest.main()

"""Regression tests for TASK-008: how the adapter and runner drive notebooklm-py generation.

Covers output language (`zh_Hant`, not the library's English default), checking the returned
GenerationStatus for quota/failure, waiting for completion, targeting downloads and renames by
the artifact id Gemini Notebook returned, quiz difficulty, quota reset-based cooldowns, and the
per-notebook source limit.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

from notebooklm import AccountLimits, GenerationStatus, QuizDifficulty, QuizQuantity, UsageSummary
from notebooklm._types.usage import UsageSummaryStatus, UsageWindow, UsageWindowKind

from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.adapters.notebooklm.quota import retry_after_from_usage
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import QuotaExceededError, StudioError
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course, Lecture
from notebooklm_batch_studio.services.artifact_runner import ArtifactRunner

CLIENT_PATH = "notebooklm_batch_studio.adapters.notebooklm.client.NotebookLMClient"


def _status(task_id: str, state: str, error_code: str | None = None) -> GenerationStatus:
    """Build a GenerationStatus the way notebooklm-py returns it.

    Args:
        task_id: Task / artifact identifier.
        state: Generation state string (pending, completed, failed).
        error_code: Optional server error code.

    Returns:
        GenerationStatus instance.
    """
    return GenerationStatus(task_id=task_id, status=state, error_code=error_code)  # type: ignore[arg-type]


class FakeArtifactsAPI:
    """Records calls made to `client.artifacts`."""

    def __init__(
        self, generate_status: GenerationStatus, final_status: GenerationStatus | None = None
    ) -> None:
        """Initialize the fake.

        Args:
            generate_status: Status returned by every generate_* call.
            final_status: Status returned by wait_for_completion (defaults to completed).
        """
        self.generate_status = generate_status
        self.final_status = final_status or _status(generate_status.task_id, "completed")
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        """Return a recording coroutine for any generate_*/download_* method.

        Args:
            name: Attribute name being looked up.

        Returns:
            Async callable recording its keyword arguments.
        """

        async def _call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, {"args": args, **kwargs}))
            if name == "wait_for_completion":
                return self.final_status
            if name.startswith("generate_"):
                return self.generate_status
            return kwargs.get("output_path", "")

        return _call

    def called(self, name: str) -> list[dict[str, Any]]:
        """List recorded calls to one method.

        Args:
            name: Method name.

        Returns:
            Recorded keyword arguments per call.
        """
        return [kw for n, kw in self.calls if n == name]


class FakeSettingsAPI:
    """Fake `client.settings` returning fixed usage and limits."""

    def __init__(self, usage: UsageSummary, limits: AccountLimits | None = None) -> None:
        """Initialize the fake.

        Args:
            usage: Usage summary returned by get_usage.
            limits: Account limits returned by get_account_limits.
        """
        self.usage = usage
        self.limits = limits or AccountLimits()

    async def get_usage(self) -> UsageSummary:
        """Return the configured usage summary.

        Returns:
            UsageSummary.
        """
        return self.usage

    async def get_account_limits(self) -> AccountLimits:
        """Return the configured account limits.

        Returns:
            AccountLimits.
        """
        return self.limits


class FakeClient:
    """Stand-in for `NotebookLMClient` used as an async context manager."""

    def __init__(self, artifacts: FakeArtifactsAPI, settings: FakeSettingsAPI) -> None:
        """Initialize the fake client.

        Args:
            artifacts: Fake artifacts API.
            settings: Fake settings API.
        """
        self.artifacts = artifacts
        self.settings = settings

    async def __aenter__(self) -> FakeClient:
        """Enter the context.

        Returns:
            This fake client.
        """
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Exit the context.

        Args:
            *exc: Exception info (ignored).
        """


class AdapterGenerationTest(unittest.IsolatedAsyncioTestCase):
    """NotebookLMAdapter must pass language, check status, wait, and return the artifact id."""

    def setUp(self) -> None:
        """Create an adapter and default fakes."""
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        cfg = AppConfig(data_dir=tmp / "data", notebooklm_home=tmp / "cfg", log_to_file=False)
        self.adapter = NotebookLMAdapter(config=cfg, storage_path=tmp / "storage_state.json")
        self.settings = FakeSettingsAPI(UsageSummary(status=UsageSummaryStatus.READY))

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.tmpdir.cleanup()

    def _patch(self, artifacts: FakeArtifactsAPI) -> Any:
        """Patch NotebookLMClient.from_storage to return the fakes.

        Args:
            artifacts: Fake artifacts API to expose.

        Returns:
            Active mock.patch context manager.
        """
        fake_cls = mock.MagicMock()
        fake_cls.from_storage.return_value = FakeClient(artifacts, self.settings)
        return mock.patch(CLIENT_PATH, fake_cls)

    async def test_audio_uses_traditional_chinese_waits_and_returns_artifact_id(self) -> None:
        """Audio is generated in zh_Hant, waited on, and identified by its artifact id."""
        arts = FakeArtifactsAPI(_status("art-audio", "pending"))
        with self._patch(arts):
            art_id = await self.adapter.generate_audio("nb", ["s1"], prompt="p", language="zh-TW")
        self.assertEqual(art_id, "art-audio")
        self.assertEqual(arts.called("generate_audio")[0]["language"], "zh_Hant")
        self.assertEqual(len(arts.called("wait_for_completion")), 1)

    async def test_every_language_aware_generator_passes_zh_hant(self) -> None:
        """Report, slides, infographic, data table, video and mind map all pass zh_Hant."""
        arts = FakeArtifactsAPI(_status("a1", "pending"))
        with self._patch(arts):
            await self.adapter.generate_report("nb", ["s1"], language="zh-TW")
            await self.adapter.generate_slide_deck("nb", ["s1"], language="zh-TW")
            await self.adapter.generate_infographic("nb", ["s1"], language="bilingual")
            await self.adapter.generate_data_table("nb", ["s1"], language="zh-TW")
            await self.adapter.generate_video("nb", ["s1"], language="zh-TW")
        for name in (
            "generate_report",
            "generate_slide_deck",
            "generate_infographic",
            "generate_data_table",
            "generate_video",
        ):
            self.assertEqual(arts.called(name)[0]["language"], "zh_Hant", name)

    async def test_report_instructions_and_concept_format(self) -> None:
        """Preset formats get our prompt as extra_instructions; concept is sent as CUSTOM. Refs: ISSUE-016"""
        from notebooklm import ReportFormat

        arts = FakeArtifactsAPI(_status("a1", "pending"))
        with self._patch(arts):
            await self.adapter.generate_report("nb", ["s1"], prompt="P", report_format="briefing_doc")
            await self.adapter.generate_report("nb", ["s1"], prompt="P", report_format="concept_explanation")
        first, second = arts.called("generate_report")
        self.assertIn("P", first["extra_instructions"])
        self.assertEqual(second["report_format"], ReportFormat.CUSTOM)
        self.assertIn("key concepts", second["custom_prompt"])

    async def test_english_course_keeps_english(self) -> None:
        """language='en' maps to the library's 'en' code."""
        arts = FakeArtifactsAPI(_status("a1", "pending"))
        with self._patch(arts):
            await self.adapter.generate_audio("nb", ["s1"], language="en")
        self.assertEqual(arts.called("generate_audio")[0]["language"], "en")

    async def test_rate_limited_status_raises_quota_with_reset_time(self) -> None:
        """A failed USER_DISPLAYABLE_ERROR status becomes QuotaExceededError timed to the window reset."""
        resets = datetime.now(timezone.utc) + timedelta(hours=2)
        self.settings.usage = UsageSummary(
            status=UsageSummaryStatus.READY,
            windows=(UsageWindow(UsageWindowKind.FIVE_HOUR, 100.0, 0.0, resets),),
        )
        arts = FakeArtifactsAPI(_status("", "failed", error_code="USER_DISPLAYABLE_ERROR"))
        with self._patch(arts), self.assertRaises(QuotaExceededError) as ctx:
            await self.adapter.generate_infographic("nb", ["s1"])
        self.assertAlmostEqual(ctx.exception.retry_after_seconds, 7200, delta=120)
        self.assertEqual(arts.called("wait_for_completion"), [], "must not wait on a rejected task")

    async def test_failed_after_wait_raises(self) -> None:
        """A task that fails while generating raises instead of downloading a stale artifact."""
        arts = FakeArtifactsAPI(_status("a1", "pending"), final_status=_status("a1", "failed"))
        with self._patch(arts), self.assertRaises(StudioError):
            await self.adapter.generate_slide_deck("nb", ["s1"])

    async def test_quiz_uses_native_difficulty_and_more_questions(self) -> None:
        """Quiz difficulty maps to QuizDifficulty and quantity is MORE."""
        arts = FakeArtifactsAPI(_status("q1", "pending"))
        with self._patch(arts):
            await self.adapter.generate_quiz("nb", ["s1"], prompt="p", difficulty="hard")
        call = arts.called("generate_quiz")[0]
        self.assertEqual(call["difficulty"], QuizDifficulty.HARD)
        self.assertEqual(call["quantity"], QuizQuantity.MORE)

    async def test_download_audio_downloads_once_by_artifact_id(self) -> None:
        """download_audio fetches exactly the requested artifact, once."""
        arts = FakeArtifactsAPI(_status("a1", "pending"))
        with self._patch(arts):
            await self.adapter.download_audio("nb", str(Path(self.tmpdir.name) / "a.mp3"), artifact_id="a1")
        calls = arts.called("download_audio")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["artifact_id"], "a1")

    async def test_source_limit_comes_from_account_limits(self) -> None:
        """get_source_limit returns the account's per-notebook source limit."""
        self.settings.limits = AccountLimits(source_limit=50)
        with self._patch(FakeArtifactsAPI(_status("a1", "pending"))):
            self.assertEqual(await self.adapter.get_source_limit(), 50)


class RetryAfterFromUsageTest(unittest.TestCase):
    """retry_after_from_usage picks the reset time of the exhausted window."""

    def test_uses_latest_exhausted_window(self) -> None:
        """When both windows are exhausted, wait for the later reset."""
        now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
        usage = UsageSummary(
            status=UsageSummaryStatus.READY,
            windows=(
                UsageWindow(UsageWindowKind.FIVE_HOUR, 100.0, 0.0, now + timedelta(hours=1)),
                UsageWindow(UsageWindowKind.WEEKLY, 100.0, 0.0, now + timedelta(days=2)),
            ),
        )
        self.assertEqual(retry_after_from_usage(usage, now), 2 * 24 * 3600)

    def test_none_when_nothing_exhausted_or_unavailable(self) -> None:
        """No exhausted window, or no live meter, yields None (caller falls back)."""
        now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
        ok = UsageSummary(
            status=UsageSummaryStatus.READY,
            windows=(UsageWindow(UsageWindowKind.FIVE_HOUR, 40.0, 60.0, now + timedelta(hours=1)),),
        )
        self.assertIsNone(retry_after_from_usage(ok, now))
        self.assertIsNone(retry_after_from_usage(UsageSummary(status=UsageSummaryStatus.DISABLED), now))


class RecordingProtocolClient:
    """NotebookLMClientProtocol fake that hands out unique artifact ids and records usage."""

    def __init__(self) -> None:
        """Initialize counters and call log."""
        self.counter = 0
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _next(self, kind: str) -> str:
        """Allocate a new artifact id.

        Args:
            kind: Artifact kind label.

        Returns:
            Unique artifact id string.
        """
        self.counter += 1
        return f"{kind}-{self.counter}"

    def __getattr__(self, name: str) -> Any:
        """Return a recording coroutine for generate_*/download_*/rename_artifact.

        Args:
            name: Attribute name.

        Returns:
            Async callable.
        """

        async def _call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, {"args": args, **kwargs}))
            if name.startswith("generate_"):
                return self._next(name.removeprefix("generate_"))
            if name.startswith("download_"):
                out = Path(args[1] if len(args) > 1 else kwargs["output_path"])
                out.parent.mkdir(parents=True, exist_ok=True)
                payload: Any = {"questions": []} if "quiz" in name else {"name": "root", "children": []}
                if "flashcards" in name:
                    payload = {"cards": []}
                out.write_text(json.dumps(payload), encoding="utf-8")
            return None

        return _call

    def called(self, name: str) -> list[dict[str, Any]]:
        """List recorded calls to one method.

        Args:
            name: Method name.

        Returns:
            Recorded call records.
        """
        return [kw for n, kw in self.calls if n == name]


class RunnerTargetingTest(unittest.IsolatedAsyncioTestCase):
    """ArtifactRunner must download and rename exactly the artifact it generated."""

    def setUp(self) -> None:
        """Create a runner with a recording client and a one-lecture course."""
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.out = tmp / "out"
        self.client = RecordingProtocolClient()
        cfg = AppConfig(data_dir=tmp / "data", notebooklm_home=tmp / "cfg", log_to_file=False)
        self.runner = ArtifactRunner(self.client, cfg)  # type: ignore[arg-type]
        self.course = Course(
            code="BIO101",
            name="細胞生物學",
            source_dir=str(tmp),
            lectures=[Lecture(no=1, topic="細胞膜", filename="01_細胞膜.pdf", sha256="a", source_id="s1")],
        )

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.tmpdir.cleanup()

    async def _run(self, art_type: ArtifactType) -> None:
        """Run one lecture job.

        Args:
            art_type: Artifact type to process.
        """
        job = ArtifactJob(id="j", course_code="BIO101", lecture_no=1, artifact_type=art_type)
        await self.runner.process_job(job, self.course, "nb", ["s1"], self.out)

    async def test_audio_download_and_rename_target_generated_artifact(self) -> None:
        """Audio download and rename use the id returned by generate_audio, never 'latest'."""
        await self._run(ArtifactType.AUDIO)
        self.assertEqual(self.client.called("download_audio")[0]["artifact_id"], "audio-1")
        self.assertEqual(self.client.called("rename_artifact")[0]["args"][1], "audio-1")
        self.assertEqual(self.client.called("find_latest_artifact"), [])
        self.assertEqual(self.client.called("generate_audio")[0]["language"], "zh-TW")

    async def test_audio_is_saved_as_m4a(self) -> None:
        """Gemini Notebook audio is MP4/AAC, so it is saved as .m4a, not .mp3. Refs: ISSUE-007"""
        await self._run(ArtifactType.AUDIO)
        out_path = self.client.called("download_audio")[0]["args"][1]
        self.assertTrue(out_path.endswith("BIO101_L01_audio.m4a"), out_path)

    async def test_study_guide_requests_study_guide_format(self) -> None:
        """STUDY_GUIDE jobs ask Gemini Notebook for the study_guide report format."""
        await self._run(ArtifactType.STUDY_GUIDE)
        self.assertEqual(self.client.called("generate_report")[0]["report_format"], "study_guide")
        self.assertEqual(self.client.called("download_report")[0]["artifact_id"], "report-1")

    async def test_quiz_variants_map_to_difficulty_and_download_by_id(self) -> None:
        """QUIZ_3 asks for hard questions and downloads each attempt by its own id."""
        with self.assertRaises(StudioError):  # empty fake quizzes -> NeedsReviewError
            await self._run(ArtifactType.QUIZ_3)
        gens = self.client.called("generate_quiz")
        downloads = self.client.called("download_quiz")
        self.assertTrue(all(g["difficulty"] == "hard" for g in gens))
        self.assertEqual([d["artifact_id"] for d in downloads], [f"quiz-{i + 1}" for i in range(len(gens))])


if __name__ == "__main__":
    unittest.main()

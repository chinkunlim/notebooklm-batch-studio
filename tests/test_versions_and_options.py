"""TASK-009 tests: mind map rename, versioned regeneration, options, device exports, auto-resume."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient
from notebooklm import InfographicOrientation, QuizQuantity
from PIL import Image

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.models import ArtifactJobRecord, utc_now
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.notebooklm.generation import generation_kwargs
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    GenerationOptions,
    JobStatus,
    Lecture,
)
from notebooklm_batch_studio.domain.naming import label_for, naming_guide, versioned_name, versioned_title
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.artifact_runner import ArtifactRunner
from notebooklm_batch_studio.services.converters.image_fitter import export_device_versions, fit_on_canvas
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.worker_pool import WorkerPool
from tests.test_notebooklm_generation import RecordingProtocolClient


class ImageRecordingClient(RecordingProtocolClient):
    """Recording client whose infographic download writes a real portrait PNG."""

    async def download_infographic(self, *args: Any, **kwargs: Any) -> None:
        """Write a 900x1600 portrait PNG with a black block in the middle.

        Args:
            *args: (notebook_id, output_path) as positional arguments.
            **kwargs: artifact_id.
        """
        self.calls.append(("download_infographic", {"args": args, **kwargs}))
        image = Image.new("RGB", (900, 1600), "white")
        image.paste(Image.new("RGB", (300, 300), "black"), (300, 650))
        image.save(args[1])


def make_course(tmp: Path, options: GenerationOptions | None = None) -> Course:
    """Build a one-lecture course with an uploaded source.

    Args:
        tmp: Temporary folder used as source dir.
        options: Optional generation options.

    Returns:
        Course entity.
    """
    return Course(
        code="BIO101",
        name="細胞生物學",
        source_dir=str(tmp),
        notebook_id="nb",
        lectures=[Lecture(no=1, topic="細胞膜", filename="01_ch_細胞膜.pdf", sha256="a", source_id="s1")],
        generation_options=options or GenerationOptions(),
    )


class NamingTest(unittest.TestCase):
    """Version suffixes and the naming guide."""

    def test_version_suffixes(self) -> None:
        """v1 is unchanged; v2 adds ' (v2)' to titles and '_v2' to file names or prefixes."""
        self.assertEqual(versioned_title("[Ch01] Infographic", 1), "[Ch01] Infographic")
        self.assertEqual(versioned_title("[Ch01] Infographic", 2), "[Ch01] Infographic (v2)")
        self.assertEqual(versioned_name("infographic.png", 2), "infographic_v2.png")
        self.assertEqual(versioned_name("quiz_1", 3), "quiz_1_v3")

    def test_guide_explains_quiz_levels(self) -> None:
        """The guide lists every quiz with its difficulty and Gemini Notebook title."""
        rows = {r["artifact_type"]: r for r in naming_guide()["artifacts"]}
        self.assertIn("easy", rows["quiz_1"]["meaning"])
        self.assertIn("hard", rows["quiz_3"]["meaning"])
        self.assertEqual(rows["quiz_2"]["notebooklm_title"], "[Ch01] Quiz 2 - Application")
        self.assertEqual(label_for(ArtifactType.QUIZ_1), "測驗 1・基礎")


class OptionsMappingTest(unittest.TestCase):
    """Course options become notebooklm-py enum arguments."""

    def test_defaults_ask_for_portrait_infographics_and_more_questions(self) -> None:
        """Default infographic orientation is portrait; quizzes ask for MORE questions."""
        self.assertEqual(
            generation_kwargs("infographic", None)["orientation"], InfographicOrientation.PORTRAIT
        )
        self.assertEqual(generation_kwargs("quiz", None)["quantity"], QuizQuantity.MORE)
        landscape = GenerationOptions(infographic_orientation="landscape")
        self.assertEqual(
            generation_kwargs("infographic", landscape)["orientation"], InfographicOrientation.LANDSCAPE
        )
        self.assertEqual(generation_kwargs("report", None), {})

    def test_short_video_forces_auto_style(self) -> None:
        """Short videos have a fixed style, so any chosen style is replaced by AUTO_SELECT."""
        from notebooklm import VideoStyle

        kwargs = generation_kwargs("video", GenerationOptions(video_format="short", video_style="anime"))
        self.assertEqual(kwargs["video_style"], VideoStyle.AUTO_SELECT)


class ImageFitterTest(unittest.TestCase):
    """Device versions keep the whole image (no cropping)."""

    def test_fit_keeps_content_and_target_size(self) -> None:
        """A portrait image on a landscape canvas is letterboxed, and its black block survives."""
        image = Image.new("RGB", (900, 1600), "white")
        image.paste(Image.new("RGB", (300, 300), "black"), (300, 650))
        fitted = fit_on_canvas(image, 3024, 1964)
        self.assertEqual(fitted.size, (3024, 1964))
        self.assertEqual(fitted.getpixel((1512, 982)), (0, 0, 0))
        self.assertEqual(fitted.getpixel((10, 982)), (255, 255, 255))

    def test_export_writes_three_device_files(self) -> None:
        """A4 PDF, iPad Air 4 and MacBook Pro 14 files are written next to the source."""
        with tempfile.TemporaryDirectory() as tmp_name:
            src = Path(tmp_name) / "infographic_v2.png"
            Image.new("RGB", (900, 1600), "white").save(src)
            names = sorted(p.name for p in export_device_versions(src))
            self.assertEqual(
                names,
                ["infographic_v2_A4.pdf", "infographic_v2_MacBookPro14.png", "infographic_v2_iPadAir4.png"],
            )
            with Image.open(Path(tmp_name) / "infographic_v2_iPadAir4.png") as ipad:
                self.assertEqual(ipad.size, (1640, 2360))


class RunnerVersionTest(unittest.IsolatedAsyncioTestCase):
    """The runner renames mind maps, names versions, and saves slides / tables with real formats."""

    def setUp(self) -> None:
        """Create a runner with an image-writing recording client."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.out = self.tmp / "out"
        self.out.mkdir()
        self.client = ImageRecordingClient()
        cfg = AppConfig(data_dir=self.tmp / "data", notebooklm_home=self.tmp / "cfg", log_to_file=False)
        self.runner = ArtifactRunner(self.client, cfg)  # type: ignore[arg-type]

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.tmpdir.cleanup()

    async def _run(
        self, art_type: ArtifactType, version: int = 1, options: GenerationOptions | None = None
    ) -> str:
        """Run one lecture job.

        Args:
            art_type: Artifact type.
            version: Job version.
            options: Course generation options.

        Returns:
            Primary output path.
        """
        job = ArtifactJob(id="j", course_code="BIO101", lecture_no=1, artifact_type=art_type, version=version)
        return await self.runner.process_job(job, make_course(self.tmp, options), "nb", ["s1"], self.out)

    async def test_mind_map_is_renamed_through_mind_map_api(self) -> None:
        """Mind maps use rename_mind_map with their note id. Refs: ISSUE-011"""
        await self._run(ArtifactType.MIND_MAP)
        renames = self.client.called("rename_mind_map")
        self.assertEqual(len(renames), 1)
        self.assertEqual(renames[0]["args"][1:], ("mind_map-1", "[Ch01] Mind Map"))
        self.assertEqual(self.client.called("rename_artifact"), [])

    async def test_v2_infographic_title_files_and_device_exports(self) -> None:
        """A regenerated infographic is '(v2)' on Gemini Notebook, '_v2' locally, with device copies."""
        path = await self._run(ArtifactType.INFOGRAPHIC, version=2)
        self.assertTrue(path.endswith("infographic_v2.png"))
        self.assertEqual(self.client.called("rename_artifact")[0]["args"][2], "[Ch01] Infographic (v2)")
        self.assertTrue((self.out / "infographic_v2_A4.pdf").exists())
        gen = self.client.called("generate_infographic")[0]
        self.assertEqual(gen["options"].infographic_orientation, "portrait")

    async def test_slide_deck_saved_as_pdf_or_pptx(self) -> None:
        """Slides keep their real format (PDF by default, PPTX when chosen). Refs: ISSUE-012"""
        self.assertTrue((await self._run(ArtifactType.SLIDE_DECK)).endswith("slide_deck.pdf"))
        pptx = await self._run(
            ArtifactType.SLIDE_DECK, version=2, options=GenerationOptions(slide_download="pptx")
        )
        self.assertTrue(pptx.endswith("slide_deck_v2.pptx"))
        self.assertEqual(self.client.called("download_slide_deck")[1]["output_format"], "pptx")

    async def test_data_table_saved_as_csv(self) -> None:
        """Gemini Notebook data tables download as CSV. Refs: ISSUE-012"""
        self.assertTrue((await self._run(ArtifactType.DATA_TABLE)).endswith("data_table.csv"))


class ServiceFixture(unittest.IsolatedAsyncioTestCase):
    """In-memory database with one course and a service."""

    def setUp(self) -> None:
        """Create database, config, course and service."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
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
        self.course_repo.save_course(make_course(self.tmp))
        self.client = RecordingProtocolClient()
        self.client.get_quota_status = mock.AsyncMock(side_effect=RuntimeError("no meter"))  # type: ignore[method-assign]
        self.service = BatchStudioService(self.course_repo, self.queue_repo, self.client, self.config)  # type: ignore[arg-type]

    def tearDown(self) -> None:
        """Close the session and remove temporary files."""
        self.session.close()
        self.tmpdir.cleanup()


class RegenerateAndOptionsTest(ServiceFixture):
    """Versioned regeneration, artifact id recording, and options persistence."""

    async def test_execute_records_artifact_ids(self) -> None:
        """execute_job stores the ids the job produced (needed for later renames). Refs: ADR-005"""
        job = ArtifactJob(id="mm", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.MIND_MAP)
        self.queue_repo.enqueue_jobs([job])
        await self.service.execute_job(job)
        stored = self.queue_repo.get_job("mm")
        assert stored is not None
        self.assertEqual(stored.artifact_ids, ("mind_map-1",))

    def test_regenerate_adds_next_version_and_keeps_old(self) -> None:
        """Two regenerations create v2 and v3 next to the existing v1 job."""
        job = ArtifactJob(id="v1", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.INFOGRAPHIC)
        self.queue_repo.enqueue_jobs([job])
        self.queue_repo.complete_job("v1", "/out/infographic.png")
        first = self.service.course_settings.regenerate("BIO101", 1, "infographic")
        second = self.service.course_settings.regenerate("BIO101", 1, "infographic")
        self.assertEqual((first["version"], second["version"]), (2, 3))
        versions = sorted(j.version for j in self.queue_repo.list_jobs(course_code="BIO101"))
        self.assertEqual(versions, [1, 2, 3])
        self.assertEqual(self.queue_repo.get_job("v1").status, JobStatus.DONE)  # type: ignore[union-attr]
        with self.assertRaises(ValueError):
            self.service.course_settings.regenerate("BIO101", 9, "infographic")

    def test_regenerate_uses_current_blueprint_not_stale_prompt(self) -> None:
        """A regenerated quiz gets today's 30-question prompt, not the older version's stored prompt."""
        old_job = ArtifactJob(
            id="q1",
            course_code="BIO101",
            lecture_no=1,
            artifact_type=ArtifactType.QUIZ_2,
            custom_prompt="出 10 題",
        )
        self.queue_repo.enqueue_jobs([old_job])
        new_id = self.service.course_settings.regenerate("BIO101", 1, "quiz_2")["job_id"]
        prompt = self.queue_repo.get_job(new_id).custom_prompt  # type: ignore[union-attr]
        self.assertIn("30 題", prompt)
        self.assertNotIn("出 10 題", prompt)

    def test_options_validate_persist_and_survive_reregistration(self) -> None:
        """Valid changes are saved; invalid values are refused; re-scanning keeps them."""
        self.service.course_settings.set_options("BIO101", {"infographic_orientation": "square"})
        with self.assertRaises(ValueError):
            self.service.course_settings.set_options("BIO101", {"infographic_orientation": "A4"})
        with self.assertRaises(ValueError):
            self.service.course_settings.set_options("BIO101", {"nope": 1})
        self.course_repo.save_course(make_course(self.tmp))  # re-registration with default options
        options = self.service.course_settings.get_options("BIO101")["options"]
        self.assertEqual(options["infographic_orientation"], "square")


class AutoResumeTest(unittest.IsolatedAsyncioTestCase):
    """Quota-blocked jobs resume on their own when the cooldown passes."""

    async def test_wait_for_quota_runs_blocked_job_after_cooldown(self) -> None:
        """With wait_for_quota, run_until_empty waits, the probe wakes the job, and it completes."""
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)

        from contextlib import contextmanager

        @contextmanager
        def provider() -> Any:
            """Yield a queue repository in its own session.

            Yields:
                QueueRepository.
            """
            with session_scope(engine) as s:
                yield QueueRepository(s)

        with provider() as repo:
            repo.enqueue_jobs(
                [ArtifactJob(id="q", course_code="C", lecture_no=1, artifact_type=ArtifactType.AUDIO)]
            )
        with session_scope(engine) as s:
            record = s.get(ArtifactJobRecord, "q")
            assert record is not None
            record.status = JobStatus.QUOTA_WAIT.value
            record.cooldown_until = utc_now() + timedelta(seconds=0.3)
            s.commit()

        executor = mock.AsyncMock(return_value="/out/a.m4a")
        pool = WorkerPool(provider, executor, concurrency=1, probe_interval_seconds=0.2)
        await asyncio.wait_for(pool.run_until_empty(idle_timeout=0.2, wait_for_quota=True), timeout=10)
        with provider() as repo:
            self.assertEqual(repo.get_job("q").status, JobStatus.DONE)  # type: ignore[union-attr]
        executor.assert_awaited_once()


class EntrypointTest(ServiceFixture):
    """HTTP routes, MCP tools, lifespan auto-start, and job rows."""

    def test_http_routes(self) -> None:
        """Naming guide, options GET/PUT (422 on bad value), regenerate, and job row fields."""
        app = create_app(config=self.config, service=self.service, study_service=mock.MagicMock())
        http = TestClient(app)
        self.assertIn("rules", http.get("/api/naming-guide").json())
        self.assertEqual(
            http.get("/api/courses/BIO101/options").json()["options"]["infographic_orientation"], "portrait"
        )
        bad = http.put("/api/courses/BIO101/options", json={"options": {"audio_format": "loud"}})
        self.assertEqual(bad.status_code, 422)
        ok = http.put("/api/courses/BIO101/options", json={"options": {"audio_format": "brief"}})
        self.assertEqual(ok.json()["options"]["audio_format"], "brief")
        regen = http.post(
            "/api/courses/BIO101/jobs/regenerate", json={"artifact_type": "infographic", "lecture_no": 1}
        )
        self.assertEqual(regen.json()["version"], 1)
        jobs = http.get("/api/courses/BIO101").json()["jobs"]
        self.assertEqual(jobs[0]["label"], "資訊圖表")
        self.assertIn("cooldown_until", jobs[0])

    def test_mcp_tools_require_confirm(self) -> None:
        """set_course_options and regenerate_artifact do nothing without confirm=True."""
        mcp = build_mcp_server(service=self.service, study_service=mock.MagicMock(), config=self.config)
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        self.assertIn("rules", json.loads(tools["get_naming_guide"].fn()))
        self.assertFalse(json.loads(tools["regenerate_artifact"].fn("BIO101", "infographic", 1))["confirmed"])
        self.assertEqual(self.queue_repo.list_jobs(course_code="BIO101"), [])
        self.assertEqual(
            json.loads(tools["regenerate_artifact"].fn("BIO101", "infographic", 1, True))["version"], 1
        )
        self.assertFalse(
            json.loads(tools["set_course_options"].fn("BIO101", {"audio_length": "long"}))["confirmed"]
        )

    def test_lifespan_starts_queue_when_enabled(self) -> None:
        """With auto_start_queue on, starting the app starts the queue."""
        cfg = AppConfig(
            data_dir=self.tmp / "data",
            notebooklm_home=self.tmp / "cfg",
            log_to_file=False,
            http_allowed_hosts=("testserver",),
            auto_start_queue=True,
        )
        service = mock.MagicMock()
        service.worker_pool = None
        with TestClient(create_app(config=cfg, service=service, study_service=mock.MagicMock())):
            service.start_queue.assert_called_once()


if __name__ == "__main__":
    unittest.main()

"""Tests: per-course pause, settings when adding, chapter range, delete course, notebook reuse."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    GenerationOptions,
    JobStatus,
    Lecture,
    parse_chapter_range,
)
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.course_settings import apply_job_settings
from notebooklm_batch_studio.services.orchestrator import BatchStudioService

LECTURES = [Lecture(no=i, topic=f"t{i}", filename=f"Ch0{i}-t{i}.pdf", sha256=str(i)) for i in (1, 2, 3, 4)]


class Fixture(unittest.TestCase):
    """Temporary course folder with 4 PDFs, an in-memory DB and a service."""

    def setUp(self) -> None:
        """Create files, database and service."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.folder = self.tmp / "BIO101 細胞生物學"
        self.folder.mkdir()
        for lec in LECTURES:
            (self.folder / lec.filename).write_bytes(b"%PDF " + lec.filename.encode())
        self.config = AppConfig(
            data_dir=self.tmp / "data",
            notebooklm_home=self.tmp / "cfg",
            log_to_file=False,
            http_allowed_hosts=("testserver",),
        )
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session = session_scope(engine).__enter__()
        self.course_repo = CourseRepository(self.session)
        self.queue_repo = QueueRepository(self.session)
        self.client = mock.MagicMock()
        self.service = BatchStudioService(self.course_repo, self.queue_repo, self.client, self.config)

    def tearDown(self) -> None:
        """Close the session and remove temporary files."""
        self.session.close()
        self.tmpdir.cleanup()


class PauseAndAddTest(Fixture):
    """Adding paused holds every job; options given at add time are stored first."""

    def test_paused_course_jobs_are_not_claimed_until_started(self) -> None:
        """A paused course's jobs are queued but neither claimed nor counted as runnable."""
        added = self.service.add_course_folders(
            [str(self.folder)], paused=True, options={"quiz_questions": 20, "extra_instructions": "考申論"}
        )
        self.assertTrue(added[0]["paused"])
        self.assertIsNone(self.queue_repo.claim_next_job(worker_id="w"))
        self.assertEqual(self.queue_repo.count_by_status(runnable_only=True)[JobStatus.PENDING], 0)
        options = self.service.course_settings.get_options("BIO101")["options"]
        self.assertEqual((options["quiz_questions"], options["extra_instructions"]), (20, "考申論"))

        self.service.course_settings.set_paused("BIO101", False)
        self.assertIsNotNone(self.queue_repo.claim_next_job(worker_id="w"))

    def test_bad_options_are_rejected(self) -> None:
        """Invalid options at add time raise before any job can run."""
        with self.assertRaises(ValueError):
            self.service.add_course_folders([str(self.folder)], options={"quiz_questions": 999})


class ChapterRangeTest(unittest.TestCase):
    """Course-wide outputs limited to some chapters."""

    def test_parse(self) -> None:
        """Ranges and lists parse; malformed text is rejected."""
        self.assertEqual(parse_chapter_range("1-3"), {1, 2, 3})
        self.assertEqual(parse_chapter_range("1, 3,5-6"), {1, 3, 5, 6})
        for bad in ("3-1", "a", "1--2", "0-2", ""):
            self.assertIsNone(parse_chapter_range(bad))

    def test_range_narrows_lectures_and_prompt(self) -> None:
        """A midterm mock exam on 1-2 keeps only those lectures and says so in the prompt."""
        course = Course(code="C", name="n", source_dir="/x", lectures=LECTURES)
        job = ArtifactJob(
            id="m",
            course_code="C",
            lecture_no=None,
            artifact_type=ArtifactType.COURSE_MOCK_EXAM,
            custom_prompt="請生成 50 題",
            style_options=json.dumps({"chapter_range": "1-2"}),
        )
        run_job, run_course = apply_job_settings(job, course)
        self.assertEqual([lec.no for lec in run_course.lectures], [1, 2])
        self.assertIn("只涵蓋第 1-2 講", run_job.custom_prompt or "")
        with self.assertRaises(ValueError):
            self.service_options_reject()

    def service_options_reject(self) -> None:
        """Helper: an invalid range is refused by option validation.

        Raises:
            ValueError: Always, from merge validation.
        """
        from notebooklm_batch_studio.domain.models import merge_generation_options

        merge_generation_options(GenerationOptions(), {"chapter_range": "3-1"})


class DeleteCourseTest(Fixture):
    """Deleting a course removes records and moves outputs aside; PDFs stay."""

    def test_delete_moves_outputs_and_keeps_pdfs(self) -> None:
        """Records are gone, outputs are under DATA_DIR/deleted/, and the input PDFs remain."""
        self.service.add_course_folders([str(self.folder)], paused=True)
        out = self.config.courses_output_dir / "BIO101" / "01_t1"
        out.mkdir(parents=True)
        (out / "quiz.json").write_text("{}", encoding="utf-8")
        result = self.service.course_settings.delete_course("BIO101")
        self.assertGreater(result["removed_jobs"], 0)
        self.assertIsNone(self.course_repo.get_course("BIO101"))
        self.assertEqual(self.queue_repo.list_jobs(course_code="BIO101"), [])
        self.assertTrue((Path(result["moved_to"]) / "BIO101" / "01_t1" / "quiz.json").exists())
        self.assertEqual(len(list(self.folder.glob("*.pdf"))), 4)

    def test_delete_cleans_keypoints_tutor_and_preferences(self) -> None:
        """Deleting a course removes its keypoints, tutor messages, and course-scoped prefs."""
        from notebooklm_batch_studio.adapters.db.models import (
            KeyPointsRecord,
            TutorMessageRecord,
            UiPreferenceRecord,
        )

        self.service.add_course_folders([str(self.folder)], paused=True)
        self.course_repo.save_course(Course(code="CHEM110", name="化學", source_dir=str(self.tmp / "chem")))
        self.session.add_all(
            [
                KeyPointsRecord(id="BIO101:1", course_code="BIO101", lecture_no=1, points_json="[]"),
                KeyPointsRecord(id="CHEM110:1", course_code="CHEM110", lecture_no=1, points_json="[]"),
                TutorMessageRecord(
                    id="tm-bio", course_code="BIO101", lecture_no=1, role="student", text="q1"
                ),
                TutorMessageRecord(
                    id="tm-chem", course_code="CHEM110", lecture_no=1, role="student", text="q2"
                ),
                UiPreferenceRecord(key="course", value="BIO101"),
                UiPreferenceRecord(key="place:BIO101", value='{"step":"s-read"}'),
                UiPreferenceRecord(key="examNotice:BIO101", value="2026-12-01"),
                UiPreferenceRecord(key="audio:BIO101:1", value="42"),
                UiPreferenceRecord(key="place:CHEM110", value='{"step":"s-quiz"}'),
                UiPreferenceRecord(key="palette", value="ink"),
            ]
        )
        self.session.commit()

        self.service.course_settings.delete_course("BIO101")

        self.assertIsNone(self.session.get(KeyPointsRecord, "BIO101:1"))
        self.assertIsNotNone(self.session.get(KeyPointsRecord, "CHEM110:1"))
        self.assertIsNone(self.session.get(TutorMessageRecord, "tm-bio"))
        self.assertIsNotNone(self.session.get(TutorMessageRecord, "tm-chem"))
        self.assertIsNone(self.session.get(UiPreferenceRecord, "course"))
        self.assertIsNone(self.session.get(UiPreferenceRecord, "place:BIO101"))
        self.assertIsNone(self.session.get(UiPreferenceRecord, "examNotice:BIO101"))
        self.assertIsNone(self.session.get(UiPreferenceRecord, "audio:BIO101:1"))
        self.assertIsNotNone(self.session.get(UiPreferenceRecord, "place:CHEM110"))
        self.assertIsNotNone(self.session.get(UiPreferenceRecord, "palette"))


class ReuseNotebookTest(Fixture):
    """Re-adding a course reuses the same-titled notebook and its uploaded PDFs."""

    def test_setup_reuses_notebook_and_sources(self) -> None:
        """No notebook is created and matching PDFs are not uploaded again."""
        import asyncio

        self.service.add_course_folders([str(self.folder)], paused=True)
        client: Any = self.client
        client.get_source_limit = mock.AsyncMock(return_value=None)
        client.find_notebook_by_title = mock.AsyncMock(return_value="nb-old")
        client.list_ready_sources = mock.AsyncMock(
            return_value={lec.filename: f"src-{lec.no}" for lec in LECTURES[:3]}
        )
        client.create_notebook = mock.AsyncMock()
        client.upload_source = mock.AsyncMock(return_value="src-new")
        client.wait_source_ready = mock.AsyncMock()
        course = asyncio.run(self.service.setup_notebook_and_sources("BIO101"))
        client.create_notebook.assert_not_called()
        self.assertEqual(client.upload_source.await_count, 1)  # only lecture 4 was missing
        self.assertEqual(course.notebook_id, "nb-old")
        self.assertEqual({lec.source_id for lec in course.lectures}, {"src-1", "src-2", "src-3", "src-new"})


class EntrypointTest(Fixture):
    """HTTP routes and MCP tools for course administration."""

    def test_http_routes(self) -> None:
        """Defaults endpoint, pause / start, delete and 404s."""
        self.service.add_course_folders([str(self.folder)], paused=True)
        http = TestClient(
            create_app(config=self.config, service=self.service, study_service=mock.MagicMock())
        )
        self.assertEqual(http.get("/api/generation-options").json()["defaults"]["quiz_questions"], 30)
        self.assertTrue(http.get("/api/courses/BIO101").json()["paused"])
        with mock.patch.object(self.service, "start_queue") as start:
            self.assertFalse(http.post("/api/courses/BIO101/start").json()["paused"])
            start.assert_called_once()
        self.assertTrue(http.post("/api/courses/BIO101/pause").json()["paused"])
        self.assertEqual(http.delete("/api/courses/BIO101").status_code, 200)
        self.assertEqual(http.delete("/api/courses/BIO101").status_code, 404)

    def test_mcp_tools_need_confirm(self) -> None:
        """delete_course and set_course_paused do nothing without confirm=True."""
        self.service.add_course_folders([str(self.folder)], paused=True)
        mcp = build_mcp_server(service=self.service, study_service=mock.MagicMock(), config=self.config)
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        self.assertFalse(json.loads(tools["delete_course"].fn("BIO101"))["confirmed"])
        self.assertIsNotNone(self.course_repo.get_course("BIO101"))
        self.assertFalse(json.loads(tools["set_course_paused"].fn("BIO101", False))["confirmed"])


class StudyStateAndCopyOptionsTest(Fixture):
    """TASK-012 study_state summary & TASK-013 copy_options across service/HTTP/MCP."""

    def test_course_summary_study_state(self) -> None:
        """Courses report not_started -> in_progress -> finished based on available study steps."""
        from notebooklm_batch_studio.adapters.db.models import StudyProgressRecord

        self.service.add_course_folders([str(self.folder)], paused=True)
        bio = next(c for c in self.service.get_courses_summary() if c["code"] == "BIO101")
        self.assertEqual(bio["study_state"], "not_started")

        jobs = self.queue_repo.list_jobs(course_code="BIO101")
        audio_job = next(j for j in jobs if j.lecture_no == 1 and j.artifact_type == ArtifactType.AUDIO)
        guide_job = next(j for j in jobs if j.lecture_no == 1 and j.artifact_type == ArtifactType.STUDY_GUIDE)
        self.queue_repo.complete_job(audio_job.id, output_file="/tmp/audio1.m4a")
        self.queue_repo.complete_job(guide_job.id, output_file="/tmp/guide1.md")

        self.session.add(StudyProgressRecord(course_code="BIO101", lecture_no=1, step="audio"))
        self.session.commit()
        bio = next(c for c in self.service.get_courses_summary() if c["code"] == "BIO101")
        self.assertEqual(bio["study_state"], "in_progress")

        self.session.add(StudyProgressRecord(course_code="BIO101", lecture_no=1, step="guide"))
        self.session.commit()
        bio = next(c for c in self.service.get_courses_summary() if c["code"] == "BIO101")
        self.assertEqual(bio["study_state"], "finished")

    def test_copy_course_options_service_http_and_mcp(self) -> None:
        """Copying course options updates options/language/mock_exam_questions while preserving exam_date."""
        chem_dir = self.tmp / "CHEM110 基礎化學"
        chem_dir.mkdir()
        (chem_dir / "Ch01-atoms.pdf").write_bytes(b"%PDF atoms")

        self.service.add_course_folders([str(self.folder), str(chem_dir)], paused=True)
        self.service.course_settings.set_options(
            "BIO101",
            {
                "quiz_questions": 20,
                "language": "en",
                "mock_exam_questions": 60,
                "exam_date": "2026-12-01",
            },
        )
        self.service.course_settings.set_options("CHEM110", {"exam_date": "2027-01-15"})

        res = self.service.course_settings.copy_options("BIO101", ["CHEM110"])
        self.assertEqual(res["copied_to"], ["CHEM110"])
        chem_opts = self.service.course_settings.get_options("CHEM110")["options"]
        self.assertEqual(chem_opts["quiz_questions"], 20)
        self.assertEqual(chem_opts["language"], "en")
        self.assertEqual(chem_opts["mock_exam_questions"], 60)
        self.assertEqual(chem_opts["exam_date"], "2027-01-15")

        # Reset and verify HTTP POST /api/courses/{code}/options/copy
        self.service.course_settings.set_options("CHEM110", {"quiz_questions": 15, "language": "zh-TW"})
        http = TestClient(
            create_app(config=self.config, service=self.service, study_service=mock.MagicMock())
        )
        resp = http.post("/api/courses/BIO101/options/copy", json={"targets": ["CHEM110"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["copied_to"], ["CHEM110"])
        chem_opts = self.service.course_settings.get_options("CHEM110")["options"]
        self.assertEqual(chem_opts["quiz_questions"], 20)
        self.assertEqual(chem_opts["exam_date"], "2027-01-15")
        self.assertEqual(http.post("/api/courses/BIO101/options/copy", json={"targets": []}).status_code, 400)

        # Reset and verify MCP confirm guard
        self.service.course_settings.set_options("CHEM110", {"quiz_questions": 10})
        mcp = build_mcp_server(service=self.service, study_service=mock.MagicMock(), config=self.config)
        tools = mcp._tool_manager._tools  # type: ignore[attr-defined]
        denied = json.loads(tools["copy_course_options"].fn("BIO101", ["CHEM110"], False))
        self.assertFalse(denied["confirmed"])
        self.assertEqual(self.service.course_settings.get_options("CHEM110")["options"]["quiz_questions"], 10)
        approved = json.loads(tools["copy_course_options"].fn("BIO101", ["CHEM110"], True))
        self.assertTrue(approved["confirmed"])
        self.assertEqual(self.service.course_settings.get_options("CHEM110")["options"]["quiz_questions"], 20)
        self.assertEqual(
            self.service.course_settings.get_options("CHEM110")["options"]["exam_date"],
            "2027-01-15",
        )


if __name__ == "__main__":
    unittest.main()

"""Tests: quiz batch titles, browser login, artifact types, view route, folder picker, weekly quota."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course, JobStatus, Lecture
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.cli import main
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.artifact_runner import ArtifactRunner
from notebooklm_batch_studio.services.folder_browser import browse_folders
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.quota_planner import estimate_quota_plan
from tests.test_notebooklm_generation import RecordingProtocolClient


class Fixture(unittest.TestCase):
    """Temporary data dir, in-memory DB and a two-lecture course (full profile)."""

    def setUp(self) -> None:
        """Create config, database, course and service."""
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
        self.course_repo.save_course(
            Course(
                code="BIO101",
                name="細胞生物學",
                source_dir=str(self.tmp),
                notebook_id="nb",
                lectures=[
                    Lecture(no=1, topic="a", filename="01_ch_a.pdf", sha256="a", source_id="s1"),
                    Lecture(no=2, topic="b", filename="02_ch_b.pdf", sha256="b", source_id="s2"),
                ],
            )
        )
        self.service = BatchStudioService(self.course_repo, self.queue_repo, mock.MagicMock(), self.config)

    def tearDown(self) -> None:
        """Close the session and remove temporary files."""
        self.session.close()
        self.tmpdir.cleanup()


class QuizBatchTitleTest(unittest.IsolatedAsyncioTestCase):
    """A quiz collected over several batches numbers its Gemini Notebook titles."""

    async def test_batches_are_numbered(self) -> None:
        """Three generated batches are renamed (1/3), (2/3), (3/3)."""
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            client = RecordingProtocolClient()
            cfg = AppConfig(data_dir=tmp / "data", notebooklm_home=tmp / "cfg", log_to_file=False)
            runner = ArtifactRunner(client, cfg)  # type: ignore[arg-type]
            course = Course(
                code="BIO101",
                name="x",
                source_dir=str(tmp),
                lectures=[Lecture(no=1, topic="a", filename="01_ch_a.pdf", sha256="a")],
            )
            job = ArtifactJob(id="q", course_code="BIO101", lecture_no=1, artifact_type=ArtifactType.QUIZ_2)
            await runner.rename_after_generation(job, course, "nb", ["a1", "a2", "a3"])
            titles = [c["args"][2] for c in client.called("rename_artifact")]
            self.assertEqual(titles[0], "[Ch01] Quiz 2 - Application (1/3)")
            self.assertEqual(titles[2], "[Ch01] Quiz 2 - Application (3/3)")
            await runner.rename_after_generation(job, course, "nb", ["only"])
            self.assertEqual(client.called("rename_artifact")[-1]["args"][2], "[Ch01] Quiz 2 - Application")


class BrowserLoginTest(unittest.TestCase):
    """`login --browser` runs notebooklm's own login; the program never handles the password."""

    def test_browser_flag_runs_notebooklm_login(self) -> None:
        """The notebooklm CLI is called with --storage pointing at the credential file."""
        with tempfile.TemporaryDirectory() as tmp_name:
            cfg = AppConfig(
                data_dir=Path(tmp_name), notebooklm_home=Path(tmp_name) / "cfg", log_to_file=False
            )
            with (
                mock.patch("notebooklm_batch_studio.entrypoints.cli.load_config", return_value=cfg),
                mock.patch("notebooklm_batch_studio.entrypoints.cli.subprocess.call", return_value=0) as call,
                mock.patch("builtins.print"),
            ):
                main(["login", "--browser"])
            args = call.call_args.args[0]
            self.assertEqual(args[1:3], ["login", "--storage"])
            self.assertTrue(args[0].endswith("notebooklm"))


class ArtifactSelectionTest(Fixture):
    """Adding and removing artifact types after a course was added."""

    def test_add_queues_and_remove_skips_unstarted_jobs(self) -> None:
        """Removing audio skips its pending jobs; adding it back revives them; new types are queued."""
        self.service.enqueue_course_artifacts("BIO101")
        settings = self.service.course_settings
        current = settings.get_artifact_selection("BIO101")
        self.assertIn("audio", current["chapter"])

        chapter = [t for t in current["chapter"] if t != "audio"] + ["data_table"]
        result = settings.set_artifact_selection("BIO101", chapter, current["course"])
        self.assertEqual(result["skipped"], 2)
        self.assertEqual(result["queued"], 2)
        audio = [
            j
            for j in self.queue_repo.list_jobs(course_code="BIO101")
            if j.artifact_type == ArtifactType.AUDIO
        ]
        self.assertTrue(all(j.status == JobStatus.SKIPPED for j in audio))

        back = settings.set_artifact_selection("BIO101", chapter + ["audio"], current["course"])
        self.assertEqual(back["revived"], 2)
        with self.assertRaises(ValueError):
            settings.set_artifact_selection("BIO101", ["course_audio"], [])

    def test_http_and_mcp(self) -> None:
        """GET/PUT /api/courses/{code}/artifact-types and the MCP tool need confirm to change."""
        http = TestClient(
            create_app(config=self.config, service=self.service, study_service=mock.MagicMock())
        )
        data = http.get("/api/courses/BIO101/artifact-types").json()
        self.assertIn("video", [c["value"] for c in data["choices"]["chapter"]])
        bad = http.put("/api/courses/BIO101/artifact-types", json={"chapter": ["nope"], "course": []})
        self.assertEqual(bad.status_code, 422)
        mcp = build_mcp_server(service=self.service, study_service=mock.MagicMock(), config=self.config)
        tool = mcp._tool_manager._tools["set_course_artifact_types"].fn  # type: ignore[attr-defined]
        self.assertFalse(json.loads(tool("BIO101", ["audio"], []))["confirmed"])


class ViewRouteTest(Fixture):
    """Study-portal view route renders Markdown and mind maps; viewable downloads are inline."""

    def test_view_and_inline_download(self) -> None:
        """A .md report and a mind map's .opml both render; other types are refused."""
        lec = self.config.courses_output_dir / "BIO101" / "01_a"
        lec.mkdir(parents=True)
        (lec / "study_guide.md").write_text("# 指南\n\n**重點**", encoding="utf-8")
        (lec / "mindmap_v2.opml").write_text("<opml/>", encoding="utf-8")
        (lec / "mindmap_v2.md").write_text("- 根\n  - 枝", encoding="utf-8")
        (lec / "anki.csv").write_text("a,b", encoding="utf-8")
        http = TestClient(
            create_app(config=self.config, service=self.service, study_service=mock.MagicMock())
        )
        page = http.get("/api/artifacts/BIO101/view/01_a/study_guide.md")
        self.assertEqual(page.status_code, 200)
        self.assertIn("<h1>指南</h1>", page.text)
        self.assertIn("<li>根", http.get("/api/artifacts/BIO101/view/01_a/mindmap_v2.opml").text)
        self.assertEqual(http.get("/api/artifacts/BIO101/view/01_a/anki.csv").status_code, 415)
        md = http.get("/api/artifacts/BIO101/download/01_a/study_guide.md")
        self.assertTrue(md.headers["content-disposition"].startswith("inline"))
        csv = http.get("/api/artifacts/BIO101/download/01_a/anki.csv")
        self.assertTrue(csv.headers["content-disposition"].startswith("attachment"))


class FolderBrowserTest(unittest.TestCase):
    """Clickable folder picker stays inside the home directory."""

    def test_shortcuts_listing_and_boundary(self) -> None:
        """Shortcuts list the input folder; sub-folders show PDF counts; outside paths are refused."""
        with tempfile.TemporaryDirectory() as tmp_name:
            home = Path(tmp_name).resolve()
            courses = home / "data" / "input" / "courses"
            course = courses / "115-1 心理學研究法"
            course.mkdir(parents=True)
            (course / "Ch01.pdf").write_bytes(b"%PDF")
            (home / "Desktop").mkdir()
            top = browse_folders(None, courses, home=home)
            self.assertEqual(
                [f["path"] for f in top["folders"]], [str(courses.resolve()), str(home / "Desktop")]
            )
            inside = browse_folders(str(courses), courses, home=home)
            self.assertEqual(inside["folders"][0]["pdf_count"], 1)
            self.assertEqual(inside["parent"], str((home / "data" / "input").resolve()))
            with self.assertRaises(ValueError):
                browse_folders("/", courses, home=home)


class WeeklyQuotaTest(unittest.TestCase):
    """The preview reports the weekly window and warns when it is nearly used up."""

    def test_weekly_warning(self) -> None:
        """Weekly remaining is shown; under 15% a warning is added."""
        quota = {
            "status": "ready",
            "windows": [
                {"kind": "five_hour", "remaining_percent": 80.0, "resets_at": "2026-11-01T10:00:00+00:00"},
                {"kind": "weekly", "remaining_percent": 9.0, "resets_at": "2026-11-03T10:00:00+00:00"},
            ],
            "actions": [{"kind": "quiz", "has_sufficient_quota": True, "estimated_cost_percent": 0.5}],
        }
        plan = estimate_quota_plan([ArtifactType.QUIZ_1], quota)
        self.assertEqual(plan["weekly_remaining_percent"], 9.0)
        self.assertIn("2026-11-03", plan["weekly_warning"])


if __name__ == "__main__":
    unittest.main()

"""SPEC-020: textbook detection, background Gemini note schedule, and quota resume at reset time."""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pypdf
from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.adapters.gemini.web_driver import GeminiQuotaExceededError
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, Course, Lecture
from notebooklm_batch_studio.domain.note_pipeline import STANDARD_NOTE_STEPS
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.notes.note_paths import ChapterNoteRequest
from notebooklm_batch_studio.services.notes.note_pipeline_service import NotePipelineService
from notebooklm_batch_studio.services.notes.note_scheduler import NoteScheduler

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
CODE = "115-1_CP30210"
ALL_STEPS = [s.step_id for s in STANDARD_NOTE_STEPS]
T0 = datetime(2026, 11, 25, 9, 0, tzinfo=UTC)


def make_book(path: Path, pages: int, outline: list[tuple[int, str, int]]) -> None:
    """Write a blank-page PDF with a nested outline.

    Args:
        path: Destination PDF path.
        pages: Number of pages.
        outline: `(level, title, 1-based page)` bookmarks.
    """
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    parents: dict[int, object] = {}
    for level, title, page in outline:
        parents[level] = writer.add_outline_item(title, page - 1, parent=parents.get(level - 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        writer.write(fh)


class FakePipeline:
    """Scripted stand-in for NotePipelineService (no browser)."""

    def __init__(self, results: list[dict[str, Any]], completed: list[str] | None = None) -> None:
        """Store scripted results.

        Args:
            results: `run_chapter` return values in call order.
            completed: `completed_steps` reported by `get_status` for the interrupted chapter.
        """
        self.results = list(results)
        self.completed = completed or []
        self.calls: list[ChapterNoteRequest] = []

    def run_chapter(self, request: ChapterNoteRequest) -> dict[str, Any]:
        """Record the request and return the next scripted result.

        Args:
            request: Chapter request.

        Returns:
            Scripted result.
        """
        self.calls.append(request)
        return self.results.pop(0)

    def get_status(self, course_key: str) -> dict[str, Any]:
        """Report chapter state like the real pipeline.

        Args:
            course_key: Course identifier.

        Returns:
            `{chapters: {chapter_id: {completed_steps}}}` for every requested chapter.
        """
        return {"chapters": {c.chapter_id: {"completed_steps": self.completed} for c in self.calls}}


def _course(course_dir: Path) -> Course:
    """Build a course with three lectures.

    Args:
        course_dir: Course folder.

    Returns:
        Course entity.
    """
    lectures = [
        Lecture(
            no=n,
            topic=f"Topic {n}",
            filename=f"Ch0{n}.pdf",
            sha256=str(n),
            source_id=f"src{n}",
            relative_path=f"02 Handouts/Ch0{n}.pdf",
        )
        for n in (1, 2, 3)
    ]
    return Course(
        code=CODE,
        name="心理學研究法",
        source_dir=str(course_dir),
        study_dir=str(course_dir),
        notebook_id="nb1",
        lectures=lectures,
    )


class SchedulerTest(unittest.TestCase):
    """Scenarios 20b and 20c (no web server)."""

    def setUp(self) -> None:
        """Temporary state file and a controllable clock."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state = Path(self.tmpdir.name) / "note_schedule.json"
        self.now = T0
        self.course = _course(Path(self.tmpdir.name) / "course")

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.tmpdir.cleanup()

    def _scheduler(self, pipeline: FakePipeline) -> NoteScheduler:
        """Build a scheduler on the fake pipeline.

        Args:
            pipeline: Fake pipeline.

        Returns:
            NoteScheduler.
        """
        return NoteScheduler(self.state, lambda: pipeline, clock=lambda: self.now)

    def test_scheduler_runs_in_order_pauses_and_recovers(self) -> None:
        """Items run in order with lecture data; duplicates skipped; pause stops; running recovers."""
        pipe = FakePipeline([{"status": "done"}, {"status": "done"}])
        sched = self._scheduler(pipe)
        self.assertEqual(sched.enqueue_course(self.course, [1, 2]), {"added": 2, "skipped": 0})
        self.assertEqual(sched.enqueue_course(self.course, [2])["skipped"], 1)
        self.assertEqual(sched.run_once(), "done")
        req = pipe.calls[0]
        self.assertEqual((req.chapter_id, req.chapter_title, req.source_ids), ("ch01", "Topic 1", ["src1"]))
        self.assertEqual(req.pdf_path, Path(self.course.source_dir) / "02 Handouts/Ch01.pdf")
        sched.pause()
        self.assertIsNone(sched.run_once())
        sched.resume()
        self.assertEqual(sched.run_once(), "done")
        self.assertIsNone(sched.run_once())
        self.assertEqual([i["status"] for i in sched.status()["items"]], ["done", "done"])
        sched.enqueue_course(self.course, [3])
        data = json.loads(self.state.read_text(encoding="utf-8"))
        data["items"][-1]["status"] = "running"
        self.state.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self._scheduler(pipe).recover(), 1)
        self.assertEqual(sched.status()["items"][-1]["status"], "pending")
        self.assertEqual(sched.clear_finished(), 2)

    def test_quota_wait_resumes_remaining_steps_at_reset_time(self) -> None:
        """Quota stop records resume_at and done modules; nothing starts early; resume runs the rest."""
        reset = T0 + timedelta(hours=2)
        pipe = FakePipeline(
            [
                {"status": "quota_wait", "resume_after": reset.isoformat()},
                {"status": "done"},
                {"status": "done"},
            ],
            completed=ALL_STEPS[:2],
        )
        sched = self._scheduler(pipe)
        sched.enqueue_course(self.course, [1, 2])
        self.assertEqual(sched.run_once(), "quota_wait")
        item = sched.status()["items"][0]
        self.assertEqual((item["resume_at"], item["completed_steps"]), (reset.isoformat(), ALL_STEPS[:2]))
        self.assertEqual(sched.status()["next_resume_at"], reset.isoformat())
        self.now = T0 + timedelta(hours=1)
        self.assertIsNone(sched.run_once())  # chapter 2 must not start while Gemini is out of quota
        self.now = reset + timedelta(minutes=1)
        self.assertEqual(sched.run_once(), "done")
        self.assertEqual(pipe.calls[-1].chapter_id, "ch01")
        self.assertEqual(pipe.calls[-1].steps_override, ALL_STEPS[2:])
        self.assertEqual(sched.run_once(), "done")
        self.assertIsNone(pipe.calls[-1].steps_override)

    def test_pipeline_reports_gemini_resume_time(self) -> None:
        """A Gemini quota error's parsed reset time is returned by run_chapter's interruption result."""
        cfg = AppConfig(data_dir=Path(self.tmpdir.name) / "data")
        cfg.ensure_data_dirs()
        svc = NotePipelineService(cfg, driver_factory=lambda *_a, **_k: None)
        reset = T0 + timedelta(hours=3)
        req = ChapterNoteRequest(course_key=CODE, course_name="x", chapter_id="ch01")
        out = svc._record_interruption(
            req, GeminiQuotaExceededError("額度已用完", raw_text="x", resume_after=reset)
        )
        self.assertEqual((out["status"], out["resume_after"]), ("quota_wait", reset.isoformat()))


class WebEntrypointsTest(unittest.TestCase):
    """Scenarios 20a and 20d."""

    def setUp(self) -> None:
        """DATA_DIR, database, one course with a textbook, and the web app."""
        self.tmpdir = tempfile.TemporaryDirectory()
        data_dir = Path(self.tmpdir.name) / "data"
        self.cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        self.cfg.ensure_data_dirs()
        self.engine = create_db_engine(self.cfg.database_url)
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)
        self.course_dir = self.cfg.study_root_dir / "115-1" / "CP__30210-心理學研究法"
        mats = self.course_dir / "01 Materials"
        make_book(mats / "Book.pdf", 9, [(1, "1 Intro", 1), (1, "2 Ethics", 4), (1, "3 Validity", 7)])
        make_book(mats / "Book" / "Ch01-Intro.pdf", 1, [])
        make_book(mats / "Scan.pdf", 2, [])
        make_book(mats / "Done.pdf", 3, [(1, "1 A", 1), (1, "2 B", 2)])
        make_book(mats / "Done" / "Ch01-A.pdf", 1, [])
        make_book(mats / "Done" / "Ch02-B.pdf", 1, [])
        (mats / "Done" / ".textbook.json").write_text("{}", encoding="utf-8")
        with self.session_factory() as session:
            CourseRepository(session).save_course(_course(self.course_dir))
            session.commit()
        self.client = TestClient(create_app(config=self.cfg))

    def tearDown(self) -> None:
        """Dispose the engine and remove temporary files."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_pending_textbooks_api_and_web(self) -> None:
        """Unsplit books are listed with chapter counts; split ones are hidden; no-outline has an error."""
        res = self.client.get("/api/textbooks/pending")
        self.assertEqual(res.status_code, 200, res.text)
        rows = {r["relative_path"]: r for r in res.json()["pending"]}
        self.assertEqual(set(rows), {"01 Materials/Book.pdf", "01 Materials/Scan.pdf"})
        book = rows["01 Materials/Book.pdf"]
        self.assertEqual((book["course_code"], book["chapters"], book["existing"]), (CODE, 3, 1))
        self.assertIn("找不到章節書籤", rows["01 Materials/Scan.pdf"]["error"])
        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        self.assertEqual(len(json.loads(tools["list_pending_textbooks"].fn())["pending"]), 2)
        js = (STATIC / "studio-textbook.js").read_text(encoding="utf-8")
        for needle in ("/api/textbooks/pending", "textbookDismissed", "預覽並切割"):
            self.assertIn(needle, js)
        self.assertIn('id="textbookPendingHost"', (STATIC / "index.html").read_text(encoding="utf-8"))

    def test_status_quota_resume_and_schedule_entrypoints(self) -> None:
        """Status exposes the earliest quota reset; schedule HTTP/MCP/web entry points work."""
        with self.session_factory() as session:
            repo = QueueRepository(session)
            repo.enqueue_jobs(
                [ArtifactJob(id="j1", course_code=CODE, lecture_no=1, artifact_type=ArtifactType.AUDIO)]
            )
            repo.block_job_quota("j1", ArtifactType.AUDIO, cooldown_seconds=1800)
        status = self.client.get("/api/status").json()
        self.assertIsNotNone(status["quota_resume_at"])
        self.assertIn("quota_resume_at", (STATIC / "studio-batch.js").read_text(encoding="utf-8"))

        cands = self.client.get(f"/api/notes/schedule/candidates/{CODE}").json()["chapters"]
        self.assertEqual([c["lecture_no"] for c in cands], [1, 2, 3])
        added = self.client.post("/api/notes/schedule", json={"course_key": CODE, "lecture_nos": [1, 3]})
        self.assertEqual(added.json(), {"added": 2, "skipped": 0})
        self.assertEqual(
            self.client.post(
                "/api/notes/schedule", json={"course_key": "NOPE", "lecture_nos": [1]}
            ).status_code,
            404,
        )
        self.assertTrue(self.client.post("/api/notes/schedule/pause").json()["paused"])
        self.assertFalse(self.client.post("/api/notes/schedule/resume").json()["paused"])
        self.assertEqual(len(self.client.get("/api/notes/schedule").json()["items"]), 2)

        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        self.assertEqual(len(json.loads(tools["notes_schedule_status"].fn())["items"]), 2)
        self.assertFalse(json.loads(tools["notes_schedule_add"].fn(CODE, [2]))["confirmed"])
        self.assertEqual(json.loads(tools["notes_schedule_add"].fn(CODE, [2], confirm=True))["added"], 1)
        js = (STATIC / "studio-note-schedule.js").read_text(encoding="utf-8")
        for needle in ("/api/notes/schedule", "開始排程", "預計"):
            self.assertIn(needle, js)
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="noteScheduleCard"', html)
        self.assertIn("studio-note-schedule.js", html)


if __name__ == "__main__":
    unittest.main()

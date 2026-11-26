"""SPEC-029: watch inside the web server, missing/changed lecture PDFs, literature auto-add, notifications."""

from __future__ import annotations

import json
import logging
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pypdf
from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.queue_repository import QueueRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import CourseStatus
from notebooklm_batch_studio.entrypoints import folder_sync
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.entrypoints.web_watch import start_web_watcher
from notebooklm_batch_studio.services.course_parser import scan_course_directory
from notebooklm_batch_studio.services.lecture_files import LectureFileChecker
from notebooklm_batch_studio.services.study_alerts import AlertNotifier, collect_alerts

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
CODE = "115-1_CP30000"


def write_pdf(path: Path, pages: int = 1) -> None:
    """Write a blank PDF (page count makes contents distinct).

    Args:
        path: Destination file.
        pages: Number of pages.
    """
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        writer.write(fh)


class Env(unittest.TestCase):
    """DATA_DIR, database and a registered handout course with two lectures."""

    def setUp(self) -> None:
        """Create the environment."""
        self.tmpdir = tempfile.TemporaryDirectory()
        data_dir = Path(self.tmpdir.name).resolve() / "data"
        self.cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
            log_to_file=False,
        )
        self.cfg.ensure_data_dirs()
        self.engine = create_db_engine(self.cfg.database_url)
        Base.metadata.create_all(self.engine)
        self.course_dir = self.cfg.study_root_dir.resolve() / "115-1" / "CP__30000-團體諮商"
        for no in (1, 2):
            write_pdf(self.course_dir / "02 Handouts" / f"0{no}_講義.pdf", no)
        with session_scope(self.engine) as session:
            CourseRepository(session).save_course(
                scan_course_directory(self.course_dir, custom_code=CODE, term="115-1")
            )

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _courses(self) -> list:  # type: ignore[type-arg]
        """Registered courses.

        Returns:
            Courses from the database.
        """
        with session_scope(self.engine) as session:
            return CourseRepository(session).list_courses()


class FileCheckTest(Env):
    """Missing and changed lecture PDFs are found; unchanged files are not rehashed."""

    def test_missing_then_restored(self) -> None:
        """A deleted lecture PDF is reported until it comes back."""
        checker = LectureFileChecker()
        pdf = self.course_dir / "02 Handouts" / "02_講義.pdf"
        data = pdf.read_bytes()
        pdf.unlink()
        issues = checker.issues(self._courses())
        self.assertEqual([(i["lecture_no"], i["issue"]) for i in issues], [(2, "missing")])
        pdf.write_bytes(data)
        self.assertEqual(checker.issues(self._courses()), [])

    def test_changed_content_reported_and_hash_cached(self) -> None:
        """Replacing a PDF's content is reported with the new hash; untouched files are hashed once."""
        calls: list[Path] = []
        from notebooklm_batch_studio.services.course_parser import compute_pdf_sha256

        def counting(path: Path) -> str:
            """Count hash calls.

            Args:
                path: PDF path.

            Returns:
                SHA-256 hex digest.
            """
            calls.append(path)
            return compute_pdf_sha256(path)

        checker = LectureFileChecker(hasher=counting)
        self.assertEqual(checker.issues(self._courses()), [])
        self.assertEqual(len(calls), 2)
        checker.issues(self._courses())
        self.assertEqual(len(calls), 2)  # nothing changed: cached
        write_pdf(self.course_dir / "02 Handouts" / "01_講義.pdf", 5)
        issues = checker.issues(self._courses())
        self.assertEqual([(i["lecture_no"], i["issue"]) for i in issues], [(1, "changed")])
        self.assertEqual(len(issues[0]["sha256"]), 64)

    def test_archived_courses_are_skipped(self) -> None:
        """Archived courses are not checked."""
        with session_scope(self.engine) as session:
            repo = CourseRepository(session)
            course = repo.get_course(CODE)
            assert course is not None
            repo.save_course(replace(course, status=CourseStatus.ARCHIVED))
        (self.course_dir / "02 Handouts" / "01_講義.pdf").unlink()
        self.assertEqual(LectureFileChecker().issues(self._courses()), [])


class NotifyTest(Env):
    """Each new item is announced once, also across restarts; off when notifications are off."""

    def _alerts(self) -> list[tuple[str, str, str]]:
        """Alerts for one new folder, one whole book and one missing lecture.

        Returns:
            `(key, title, message)` tuples.
        """
        folders = [{"term": "115-2", "folder": "專題製作", "path": "/x/專題製作", "needs_course_no": True}]
        books = [{"course_code": CODE, "course_name": "團體諮商", "relative_path": "01 Materials/Book.pdf"}]
        issues = [{"course_code": CODE, "course_name": "團體諮商", "lecture_no": 2, "filename": "02.pdf",
                   "issue": "missing", "sha256": ""}]  # fmt: skip
        return collect_alerts(folders, books, issues)

    def test_once_per_item_and_across_restart(self) -> None:
        """Two passes and a restart send three notifications in total."""
        sent: list[tuple[str, str]] = []
        state = self.cfg.study_alerts_path
        AlertNotifier(state, lambda t, m: sent.append((t, m))).notify_new(self._alerts())
        AlertNotifier(state, lambda t, m: sent.append((t, m))).notify_new(self._alerts())
        self.assertEqual(len(sent), 3)
        self.assertTrue(any("專題製作" in m for _, m in sent))
        self.assertTrue(any("講義遺失" in m for _, m in sent))
        self.assertTrue(any("Book.pdf" in m for _, m in sent))
        self.assertEqual(len(json.loads(state.read_text(encoding="utf-8"))), 3)

    def test_changed_twice_notifies_twice(self) -> None:
        """A second content change (new hash) is a new item."""
        base = {
            "course_code": CODE,
            "course_name": "團體諮商",
            "lecture_no": 1,
            "filename": "01.pdf",
            "issue": "changed",
        }
        sent: list[str] = []
        notifier = AlertNotifier(self.cfg.study_alerts_path, lambda t, m: sent.append(m))
        notifier.notify_new(collect_alerts([], [], [{**base, "sha256": "a" * 64}]))
        notifier.notify_new(collect_alerts([], [], [{**base, "sha256": "b" * 64}]))
        self.assertEqual(len(sent), 2)
        self.assertIn("講義已更新", sent[0])


class BackgroundPassTest(Env):
    """One background pass: folders, literature, alerts; a failing step does not stop the others."""

    def test_pass_adds_literature_and_notifies(self) -> None:
        """A PDF in scratch/literature joins the list; a missing lecture is announced (no network)."""
        write_pdf(self.cfg.scratch_kind_dir("literature") / "Smith_2020.pdf")
        (self.course_dir / "02 Handouts" / "02_講義.pdf").unlink()
        cfg = replace(self.cfg, notify_on_complete=True)
        sent: list[str] = []
        with mock.patch("httpx.Client.send", side_effect=AssertionError("no network")):
            run_once = folder_sync.build_pass(
                cfg, make_session_factory(self.engine), lambda t, m: sent.append(m)
            )
            run_once()
        from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository

        with session_scope(self.engine) as session:
            files = [i.file for i in LiteratureRepository(session).list_items()]
        self.assertIn("Smith_2020.pdf", files)
        self.assertTrue(any("講義遺失" in m for m in sent))

    def test_notifications_off(self) -> None:
        """With notifications off nothing is sent."""
        (self.course_dir / "02 Handouts" / "02_講義.pdf").unlink()
        sent: list[str] = []
        folder_sync.build_pass(self.cfg, make_session_factory(self.engine), lambda t, m: sent.append(m))()
        self.assertEqual(sent, [])

    def test_failing_step_does_not_stop_others(self) -> None:
        """If the folder step raises, literature still gets registered."""
        write_pdf(self.cfg.scratch_kind_dir("literature") / "Lee_2021.pdf")
        with mock.patch.object(folder_sync, "sync_new_study_folders", side_effect=RuntimeError("boom")):
            folder_sync.build_pass(self.cfg, make_session_factory(self.engine), lambda t, m: None)()
        from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository

        with session_scope(self.engine) as session:
            self.assertIn("Lee_2021.pdf", [i.file for i in LiteratureRepository(session).list_items()])


class WebWatchTest(Env):
    """The web server watches study/ when WATCH_IN_WEB is on."""

    def test_off_by_default(self) -> None:
        """AppConfig default does not start a watcher."""
        self.assertIsNone(start_web_watcher(self.cfg, self.engine))

    def test_new_handout_is_registered_and_scheduled(self) -> None:
        """With the watcher on, a new 02 Handouts PDF becomes lecture 3 with jobs."""
        watcher = start_web_watcher(replace(self.cfg, watch_in_web=True), self.engine)
        assert watcher is not None
        try:
            time.sleep(1)
            write_pdf(self.course_dir / "02 Handouts" / "03_講義.pdf", 3)
            # Wait for lecture 3 itself: macOS may also deliver late "created" events for the files setUp
            # wrote just before the watcher started, which queue jobs for lectures 1–2 first.
            deadline = time.monotonic() + 20
            lectures, jobs = 0, 0
            while time.monotonic() < deadline and not (lectures == 3 and jobs):
                with session_scope(self.engine) as session:
                    course = CourseRepository(session).get_course(CODE)
                    lectures = len(course.lectures) if course else 0
                    jobs = len(QueueRepository(session).list_jobs(course_code=CODE))
                time.sleep(0.3)
        finally:
            watcher.stop()
        with session_scope(self.engine) as session:
            course = CourseRepository(session).get_course(CODE)
        assert course is not None
        self.assertEqual(len(course.lectures), 3)
        self.assertGreater(jobs, 0)


class EntrypointTest(Env):
    """HTTP, MCP and the 批次排程 card for lecture file issues."""

    def test_http_mcp_card(self) -> None:
        """All three expose missing/changed lecture PDFs."""
        (self.course_dir / "02 Handouts" / "02_講義.pdf").unlink()
        body = TestClient(create_app(config=self.cfg)).get("/api/study/lecture-file-issues").json()
        self.assertEqual([(i["lecture_no"], i["issue"]) for i in body["issues"]], [(2, "missing")])
        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        self.assertEqual(json.loads(tools["list_lecture_file_issues"].fn())["issues"][0]["issue"], "missing")
        js = (STATIC / "studio-textbook.js").read_text(encoding="utf-8")
        self.assertIn("/api/study/lecture-file-issues", js)
        self.assertIn("講義遺失", js)
        self.assertIn("講義已更新", js)
        self.assertIn("lectureIssueHost", (STATIC / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

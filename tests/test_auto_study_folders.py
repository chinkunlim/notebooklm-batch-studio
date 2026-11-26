"""SPEC-028: new folders under study/<term>/ are found as subjects and get 01–05 automatically."""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path

import pypdf
from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import CourseStatus, ProfileName
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.course_parser import scan_course_directory
from notebooklm_batch_studio.services.course_placement import prepare_course_for_registration
from notebooklm_batch_studio.services.new_course_folders import FolderSyncLoop, sync_new_study_folders

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
CATEGORIES = ["01 Materials", "02 Handouts", "03 Notes", "04 Homework", "05 Assignments"]


def write_pdf(path: Path) -> None:
    """Write a one-page blank PDF.

    Args:
        path: Destination file.
    """
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        writer.write(fh)


def dirs(folder: Path) -> list[str]:
    """Sorted sub-folder names.

    Args:
        folder: Folder to list.

    Returns:
        Names of its sub-folders.
    """
    return sorted(p.name for p in folder.iterdir() if p.is_dir())


class AutoFoldersTest(unittest.TestCase):
    """One registered course in 115-1; new 115-2 subjects appear and get filled."""

    def setUp(self) -> None:
        """Create DATA_DIR, database, a registered 115-1 course and new 115-2 subject folders."""
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
        self.study = self.cfg.study_root_dir.resolve()
        registered = self.study / "115-1" / "CP__31000-生涯諮商與實務"
        write_pdf(registered / "02 Handouts" / "a.pdf")
        with session_scope(self.engine) as session:
            CourseRepository(session).save_course(
                scan_course_directory(registered, custom_code="115-1_CP31000", term="115-1")
            )
        self.registered = registered
        self.project = self.study / "115-2" / "專題製作"
        self.project.mkdir(parents=True)
        self.school = self.study / "115-2" / "CP__40000-新課"
        write_pdf(self.school / "01_第一講.pdf")

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _sync(self) -> list[dict[str, object]]:
        """Run one automatic pass.

        Returns:
            Detected subjects.
        """
        with session_scope(self.engine) as session:
            return sync_new_study_folders(self.cfg, CourseRepository(session))

    def test_subjects_found_and_filled(self) -> None:
        """Both 115-2 folders get 01–05; the school one keeps its PDF; 專題製作 needs a course number."""
        found = self._sync()
        by_folder = {f["folder"]: f for f in found}
        self.assertEqual(sorted(by_folder), ["CP__40000-新課", "專題製作"])
        self.assertEqual(dirs(self.project), CATEGORIES)
        self.assertEqual(dirs(self.school), CATEGORIES)
        self.assertTrue((self.school / "01_第一講.pdf").is_file())
        self.assertTrue(by_folder["專題製作"]["needs_course_no"])
        self.assertEqual((by_folder["專題製作"]["code"], by_folder["專題製作"]["name"]), ("", "專題製作"))
        self.assertFalse(by_folder["CP__40000-新課"]["needs_course_no"])
        self.assertEqual(by_folder["CP__40000-新課"]["course_no"], "CP40000")

    def test_leaves_other_places_alone(self) -> None:
        """Older unregistered terms and non-term folders are not touched."""
        old = self.study / "114-2" / "舊科目"
        old.mkdir(parents=True)
        odd = self.study / "雜項" / "某資料夾"
        odd.mkdir(parents=True)
        self._sync()
        self.assertEqual(dirs(old), [])
        self.assertEqual(dirs(odd), [])

    def test_registered_active_courses_are_filled_archived_are_not(self) -> None:
        """Registered, not archived courses also get their missing 01–05; archived ones stay as they are."""
        self.assertEqual(dirs(self.registered), ["02 Handouts"])
        archived = self.study / "113-1" / "CP__10000-舊課"
        write_pdf(archived / "02 Handouts" / "x.pdf")
        with session_scope(self.engine) as session:
            course = scan_course_directory(archived, custom_code="113-1_CP10000", term="113-1")
            CourseRepository(session).save_course(replace(course, status=CourseStatus.ARCHIVED))
        self._sync()
        self.assertEqual(dirs(self.registered), CATEGORIES)
        self.assertTrue((self.registered / "02 Handouts" / "a.pdf").is_file())
        self.assertEqual(dirs(archived), ["02 Handouts"])

    def test_loop_runs_now_and_stops(self) -> None:
        """The background loop runs at start, repeats, and stops cleanly."""
        calls: list[float] = []
        done = threading.Event()

        def run_once() -> None:
            """Record one pass.

            Raises:
                RuntimeError: Never; errors inside must not kill the loop (tested by the second call).
            """
            calls.append(time.monotonic())
            if len(calls) == 1:
                raise RuntimeError("first pass fails")
            done.set()

        loop = FolderSyncLoop(run_once, interval=0.05)
        loop.start()
        self.assertTrue(done.wait(2))
        loop.stop()
        self.assertGreaterEqual(len(calls), 2)

    def test_web_server_fills_on_startup(self) -> None:
        """Starting the web app runs a pass right away."""
        with TestClient(create_app(config=self.cfg)):
            deadline = time.monotonic() + 3
            while dirs(self.project) != CATEGORIES and time.monotonic() < deadline:
                time.sleep(0.05)
        self.assertEqual(dirs(self.project), CATEGORIES)

    def test_add_folder_without_course_number(self) -> None:
        """專題製作 is added with the typed course number; without one it is refused; folder name kept."""
        with self.assertRaises(ValueError):
            prepare_course_for_registration(str(self.project), ProfileName.FULL, {"term": "115-2"}, self.cfg)
        opts = {"term": "115-2", "course_no": "xx10000", "course_name": "專題製作"}
        course = prepare_course_for_registration(str(self.project), ProfileName.FULL, opts, self.cfg)
        self.assertEqual((course.code, course.name, course.term), ("115-2_XX10000", "專題製作", "115-2"))
        self.assertTrue(self.project.is_dir())

    def test_entrypoints(self) -> None:
        """HTTP and MCP report needs_course_no; the card shows it."""
        body = TestClient(create_app(config=self.cfg)).get("/api/study/new-course-folders").json()
        self.assertIn(True, [f["needs_course_no"] for f in body["folders"]])
        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        mcp = json.loads(tools["list_new_course_folders"].fn())["folders"]
        self.assertEqual(sorted(f["folder"] for f in mcp), ["CP__40000-新課", "專題製作"])
        js = (STATIC / "studio-textbook.js").read_text(encoding="utf-8")
        self.assertIn("needs_course_no", js)
        self.assertIn("需要課號", js)


if __name__ == "__main__":
    unittest.main()

"""SPEC-027: new course folders are suggested, adding creates 01–05, and watch follows textbook chapters."""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pypdf
from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.queue_repository import QueueRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import CourseStatus, ProfileName
from notebooklm_batch_studio.domain.textbook_sections import TEXTBOOK_MARKER
from notebooklm_batch_studio.entrypoints import cli
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.course_parser import scan_course_directory
from notebooklm_batch_studio.services.course_placement import prepare_course_for_registration
from notebooklm_batch_studio.services.new_course_folders import find_new_course_folders
from notebooklm_batch_studio.services.watcher import watch_kind

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
CATEGORIES = ["01 Materials", "02 Handouts", "03 Notes", "04 Homework", "05 Assignments"]


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


class Base_(unittest.TestCase):
    """Temporary DATA_DIR, database, and one active textbook course in 115-1."""

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
        self.study = self.cfg.study_root_dir.resolve()
        self.active = self.study / "115-1" / "CP__31000-生涯諮商與實務"
        self.book = self.active / "01 Materials" / "Career Counseling"
        for n in (1, 2):
            write_pdf(self.book / f"Ch0{n}-Topic.pdf", n)
        (self.book / TEXTBOOK_MARKER).write_text(json.dumps({"chapters": []}), encoding="utf-8")
        (self.active / "02 Handouts").mkdir(parents=True)
        course = scan_course_directory(self.active, custom_code="115-1_CP31000", term="115-1")
        with session_scope(self.engine) as session:
            CourseRepository(session).save_course(course)

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _new_folders(self) -> list[dict[str, object]]:
        """Run the detection on a fresh session.

        Returns:
            Detected folders.
        """
        with session_scope(self.engine) as session:
            return find_new_course_folders(self.cfg, CourseRepository(session))


class DetectionTest(Base_):
    """Only unregistered course folders of the current term or later are suggested."""

    def test_only_current_term_or_later(self) -> None:
        """115-2 new folder is listed; an old 114-2 folder is not."""
        write_pdf(self.study / "115-2" / "CP__40000-新課" / "01_第一講.pdf")
        write_pdf(self.study / "114-2" / "CP__20000-舊課" / "02 Handouts" / "a.pdf")
        found = self._new_folders()
        self.assertEqual(
            [(f["term"], f["folder"], f["code"]) for f in found],
            [("115-2", "CP__40000-新課", "115-2_CP40000")],
        )
        self.assertEqual(found[0]["path"], str(self.study / "115-2" / "CP__40000-新課"))
        self.assertEqual(found[0]["lecture_count"], 1)

    def test_same_term_unregistered_folder_is_listed(self) -> None:
        """A new folder in the current term counts too; registered ones never do."""
        write_pdf(self.study / "115-1" / "GC__68210-新選修" / "02 Handouts" / "w1.pdf")
        self.assertEqual([f["folder"] for f in self._new_folders()], ["GC__68210-新選修"])

    def test_without_active_courses_uses_newest_term(self) -> None:
        """When every course is archived, the newest term in study/ decides."""
        with session_scope(self.engine) as session:
            repo = CourseRepository(session)
            course = repo.get_course("115-1_CP31000")
            assert course is not None
            from dataclasses import replace

            repo.save_course(replace(course, status=CourseStatus.ARCHIVED))
        write_pdf(self.study / "114-2" / "CP__20000-舊課" / "a.pdf")
        write_pdf(self.study / "116-1" / "CP__50000-更新的課" / "a.pdf")
        self.assertEqual([f["term"] for f in self._new_folders()], ["116-1"])


class EnsureTreeTest(Base_):
    """Adding a folder already inside study/ creates the five category folders; preview does not."""

    def test_add_creates_categories_and_keeps_top_level_pdf(self) -> None:
        """01–05 appear, the loose PDF stays put and is still a lecture."""
        folder = self.study / "115-2" / "CP__40000-新課"
        write_pdf(folder / "01_第一講.pdf")
        course = prepare_course_for_registration(str(folder), ProfileName.FULL, {}, self.cfg)
        self.assertEqual(sorted(p.name for p in folder.iterdir() if p.is_dir()), CATEGORIES)
        self.assertTrue((folder / "01_第一講.pdf").is_file())
        self.assertEqual([lec.filename for lec in course.lectures], ["01_第一講.pdf"])

    def test_preview_creates_nothing(self) -> None:
        """The wizard preview leaves the folder untouched."""
        folder = self.study / "115-2" / "CP__40000-新課"
        write_pdf(folder / "01_第一講.pdf")
        client = TestClient(create_app(config=self.cfg))
        res = client.post("/api/courses/preview", json={"folders": [str(folder)]})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual([p.name for p in folder.iterdir()], ["01_第一講.pdf"])


class WatchTest(Base_):
    """watch follows the lecture source: new chapters become lectures (not scheduled), books get a hint."""

    def _detect(self, rel: str) -> str:
        """Drop a PDF and run the watch callback.

        Args:
            rel: Course-relative path.

        Returns:
            Printed output.
        """
        pdf = self.active / rel
        write_pdf(pdf, 7)
        env = cli._BatchEnv(self.engine, mock.Mock(), self.cfg)
        with mock.patch("builtins.print") as printed:
            cli._on_pdf_detected(self.active, pdf, env)
        return " ".join(str(c.args[0]) for c in printed.call_args_list)

    def _lectures_and_jobs(self) -> tuple[list[str], int]:
        """Stored lecture files and job count.

        Returns:
            `(filenames, jobs)`.
        """
        with session_scope(self.engine) as session:
            course = CourseRepository(session).get_course("115-1_CP31000")
            jobs = len(QueueRepository(session).list_jobs(course_code="115-1_CP31000"))
        assert course is not None
        return [lec.filename for lec in course.lectures], jobs

    def test_kinds(self) -> None:
        """The watcher recognises handouts, chapter folders and whole books; ignores the rest."""
        layout = self.cfg.study_layout
        cases = {
            "02 Handouts/w1.pdf": "handout",
            "01 Materials/Career Counseling/Ch03-New.pdf": "chapter",
            "01 Materials/Whole Book.pdf": "textbook",
            "01 Materials/Literature_Review/paper.pdf": None,
            "04 Homework/hw.pdf": None,
        }
        for rel, kind in cases.items():
            with self.subTest(rel=rel):
                self.assertEqual(watch_kind(self.active, self.active / rel, layout), kind)

    def test_new_chapter_becomes_lecture_without_jobs(self) -> None:
        """Ch03 dropped into the chapter folder is lecture 3; nothing is queued."""
        out = self._detect("01 Materials/Career Counseling/Ch03-New.pdf")
        files, jobs = self._lectures_and_jobs()
        self.assertEqual(files, ["Ch01-Topic.pdf", "Ch02-Topic.pdf", "Ch03-New.pdf"])
        self.assertEqual(jobs, 0)
        self.assertIn("開始生成", out)

    def test_whole_book_only_prints_a_hint(self) -> None:
        """A book at the top of 01 Materials is not split or registered."""
        out = self._detect("01 Materials/Whole Book.pdf")
        self.assertEqual(self._lectures_and_jobs(), (["Ch01-Topic.pdf", "Ch02-Topic.pdf"], 0))
        self.assertIn("預覽並切割", out)
        self.assertFalse((self.active / "01 Materials" / "Whole Book").exists())

    def test_watcher_forwards_materials_events(self) -> None:
        """The file-system handler passes chapter and book PDFs to the callback, not literature."""
        from notebooklm_batch_studio.services.watcher import CoursePdfEventHandler

        got: list[str] = []
        handler = CoursePdfEventHandler(
            self.study, lambda p: self.active, lambda c, p: got.append(p.name), layout=self.cfg.study_layout
        )
        for rel in (
            "01 Materials/Career Counseling/Ch03-New.pdf",
            "01 Materials/Lit/x.pdf",
            "01 Materials/Book.pdf",
        ):
            write_pdf(self.active / rel)
            with mock.patch(
                "notebooklm_batch_studio.services.watcher._wait_for_file_settled", return_value=True
            ):
                handler._process_event_path(self.active / rel)
        self.assertEqual(got, ["Ch03-New.pdf", "Book.pdf"])


class EntrypointTest(Base_):
    """HTTP, MCP and the 批次排程 card."""

    def test_http_mcp_and_card(self) -> None:
        """All three entry points expose the detection; the card opens the wizard with the folder."""
        write_pdf(self.study / "115-2" / "CP__40000-新課" / "a.pdf")
        body = TestClient(create_app(config=self.cfg)).get("/api/study/new-course-folders").json()
        self.assertEqual([f["code"] for f in body["folders"]], ["115-2_CP40000"])
        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        self.assertEqual(
            json.loads(tools["list_new_course_folders"].fn())["folders"][0]["folder"], "CP__40000-新課"
        )
        js = (STATIC / "studio-textbook.js").read_text(encoding="utf-8")
        self.assertIn("/api/study/new-course-folders", js)
        self.assertIn("addPickedFolder", js)
        wizard = (STATIC / "studio-wizard.js").read_text(encoding="utf-8")
        self.assertIn("loadNewCourseFolders", wizard)  # the card disappears right after adding


if __name__ == "__main__":
    unittest.main()

"""SPEC-025 R4a: a course that uses textbook chapters as lectures keeps them when a handout PDF appears."""

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
from notebooklm_batch_studio.domain.textbook_sections import TEXTBOOK_MARKER
from notebooklm_batch_studio.entrypoints import cli
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.course_parser import (
    ignored_handouts,
    keep_lecture_source,
    scan_course_directory,
)
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.textbook_split import TextbookService

logger = logging.getLogger(__name__)

CODE = "115-1_CP31000"
CHAPTERS = ["Ch01-Intro.pdf", "Ch02-Theory.pdf", "Ch03-Practice.pdf"]


def write_pdf(path: Path, pages: int) -> None:
    """Write a blank PDF whose page count makes its content (sha256) distinct.

    Args:
        path: Destination file.
        pages: Number of blank pages.
    """
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        writer.write(fh)


class LectureSourceGuardTest(unittest.TestCase):
    """Textbook-chapter lectures survive a handout PDF; handout courses are unaffected."""

    def setUp(self) -> None:
        """Create DATA_DIR, database and a course whose lectures are textbook chapters."""
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
        self.course_dir = self.cfg.study_root_dir / "115-1" / "CP__31000-生涯諮商與實務"
        self.handouts = self.course_dir / "02 Handouts"
        self.handouts.mkdir(parents=True)
        book = self.course_dir / "01 Materials" / "Career Counseling"
        for pages, name in enumerate(CHAPTERS, start=1):
            write_pdf(book / name, pages)
        (book / TEXTBOOK_MARKER).write_text(
            json.dumps({"source": "", "chapters": CHAPTERS}), encoding="utf-8"
        )
        self.existing = scan_course_directory(self.course_dir, custom_code=CODE, term="115-1")
        with session_scope(self.engine) as session:
            CourseRepository(session).save_course(self.existing)

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _stored_filenames(self) -> list[str]:
        """Return the stored lecture file names in lecture order.

        Returns:
            File names.
        """
        with session_scope(self.engine) as session:
            course = CourseRepository(session).get_course(CODE)
        assert course is not None
        return [lec.filename for lec in course.lectures]

    def test_setup_uses_textbook_chapters(self) -> None:
        """Baseline: with 02 Handouts empty the three chapters are the lectures."""
        self.assertEqual([lec.filename for lec in self.existing.lectures], CHAPTERS)

    def test_handout_does_not_replace_textbook_lectures(self) -> None:
        """A handout PDF in a textbook course leaves the chapter lectures as they are."""
        write_pdf(self.handouts / "week1.pdf", 7)
        scanned = scan_course_directory(self.course_dir, custom_code=CODE, term="115-1")
        kept = keep_lecture_source(scanned, self.existing)
        self.assertEqual(
            [(lec.no, lec.filename) for lec in kept.lectures],
            [(1, CHAPTERS[0]), (2, CHAPTERS[1]), (3, CHAPTERS[2])],
        )
        self.assertEqual(ignored_handouts(kept), ["02 Handouts/week1.pdf"])

    def test_handout_course_keeps_using_handouts(self) -> None:
        """A course whose lectures are handouts is not switched to textbook chapters."""
        write_pdf(self.handouts / "week1.pdf", 7)
        handout_course = scan_course_directory(self.course_dir, custom_code=CODE, term="115-1")
        kept = keep_lecture_source(handout_course, handout_course)
        self.assertEqual([lec.filename for lec in kept.lectures], ["week1.pdf"])
        self.assertEqual(ignored_handouts(kept), [])

    def test_new_course_without_history_is_unchanged(self) -> None:
        """No stored course means the normal scan rule applies."""
        write_pdf(self.handouts / "week1.pdf", 7)
        scanned = scan_course_directory(self.course_dir, custom_code=CODE, term="115-1")
        self.assertIs(keep_lecture_source(scanned, None), scanned)

    def test_watch_skips_handout_in_textbook_course(self) -> None:
        """The watch callback does not rescan or enqueue when a handout lands in a textbook course."""
        pdf = self.handouts / "week1.pdf"
        write_pdf(pdf, 7)
        env = cli._BatchEnv(self.engine, mock.Mock(), self.cfg)
        cli._on_pdf_detected(self.course_dir, pdf, env)
        self.assertEqual(self._stored_filenames(), CHAPTERS)
        with session_scope(self.engine) as session:
            self.assertEqual(QueueRepository(session).list_jobs(course_code=CODE), [])

    def test_add_course_folders_keeps_textbook_lectures(self) -> None:
        """Re-adding a textbook course whose 02 Handouts got a PDF keeps the chapter lectures."""
        write_pdf(self.handouts / "week1.pdf", 7)
        with session_scope(self.engine) as session:
            repo = CourseRepository(session)
            service = BatchStudioService(repo, QueueRepository(session), mock.MagicMock(), self.cfg)
            service.add_course_folders([str(self.course_dir)], term="115-1", paused=True)
        self.assertEqual(self._stored_filenames(), CHAPTERS)

    def test_register_course_folder_keeps_textbook_lectures(self) -> None:
        """The simple folder registration keeps the chapter lectures too."""
        write_pdf(self.handouts / "week1.pdf", 7)
        with session_scope(self.engine) as session:
            repo = CourseRepository(session)
            service = BatchStudioService(repo, QueueRepository(session), mock.MagicMock(), self.cfg)
            with mock.patch.object(repo, "get_course", return_value=self.existing):
                course = service.register_course_folder(self.course_dir)
        self.assertEqual([lec.filename for lec in course.lectures], CHAPTERS)

    def test_split_sync_adds_new_chapter_despite_handout(self) -> None:
        """After a split adds Ch04, lectures refresh from chapters even with a handout present."""
        write_pdf(self.handouts / "week1.pdf", 7)
        write_pdf(self.course_dir / "01 Materials" / "Career Counseling" / "Ch04-More.pdf", 4)
        with session_scope(self.engine) as session:
            repo = CourseRepository(session)
            TextbookService(self.cfg, repo, mock.Mock())._sync_textbook_lectures(
                self.existing, self.course_dir
            )
        self.assertEqual(self._stored_filenames(), [*CHAPTERS, "Ch04-More.pdf"])

    def test_pending_textbooks_report_ignored_handouts_on_all_entrypoints(self) -> None:
        """HTTP, MCP and the web card all surface handouts that are not lectures."""
        write_pdf(self.handouts / "week1.pdf", 7)
        expected = [
            {"course_code": CODE, "course_name": self.existing.name, "files": ["02 Handouts/week1.pdf"]}
        ]
        body = TestClient(create_app(config=self.cfg)).get("/api/textbooks/pending").json()
        self.assertEqual(body["ignored_handouts"], expected)
        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        self.assertEqual(json.loads(tools["list_pending_textbooks"].fn())["ignored_handouts"], expected)
        static = (
            Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
        )
        self.assertIn("ignored_handouts", (static / "studio-textbook.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

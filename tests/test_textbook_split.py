"""SPEC-018: textbook chapter detection, pypdf splitting, lecture source rule, relocation, entry points."""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pypdf
from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.adapters.pdf_textbook import PypdfTextbookTools
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.generation_options import GenerationOptions
from notebooklm_batch_studio.domain.models import Course, Lecture, ProfileName
from notebooklm_batch_studio.domain.textbook_sections import (
    OutlineEntry,
    PageRangeJob,
    chapter_filename,
    find_chapter_sections,
)
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.job_planner import list_material_source_pdfs
from notebooklm_batch_studio.services.textbook_split import TextbookService

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
CODE = "115-1_CP30210"
OUTLINE = [
    (1, "Contents", 2),
    (1, "Part I Introduction", 3),
    (2, "1 Introduction to Scientific Research", 3),
    (3, "1.1 Compare Methods", 4),
    (2, "2 Research Approaches: Methods of Data Collection", 6),
    (1, "Part II Planning", 9),
    (2, "3 Ethics", 9),
    (1, "References", 12),
]


def make_book(path: Path, pages: int, outline: list[tuple[int, str, int]]) -> None:
    """Write a blank-page PDF with a nested outline.

    Args:
        path: Destination PDF path.
        pages: Number of pages.
        outline: `(level, title, 1-based page)` bookmarks in order.
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


class SectionsTest(unittest.TestCase):
    """Scenarios 18a and 18b (no database)."""

    def test_find_chapter_sections_handles_parts_subsections_and_filenames(self) -> None:
        """Chapters come from the level with most matches; '1.1' is ignored; ends stop at Part/References."""
        entries = [OutlineEntry(*e) for e in OUTLINE]
        sections = find_chapter_sections(entries, total_pages=13)
        self.assertEqual(
            [(s.number, s.title, s.start, s.end) for s in sections],
            [
                (1, "Introduction to Scientific Research", 3, 5),
                (2, "Research Approaches: Methods of Data Collection", 6, 8),
                (3, "Ethics", 9, 11),
            ],
        )
        self.assertEqual(sections[1].filename, "Ch02-Research-Approaches-Methods-of-Data-Collection.pdf")
        self.assertEqual(
            chapter_filename(4, "Empowering Women’s Life Choices: An  Examination"),
            "Ch04-Empowering-Women’s-Life-Choices-An-Examination.pdf",
        )
        self.assertEqual(
            chapter_filename(16, "Using Information, Taking Action, and Developing Plans of Action"),
            "Ch16-Using-Information-Taking-Action-and-Developing-Plans-of-Action.pdf",
        )
        chapter_titled = [OutlineEntry(1, "Chapter 7 Groups", 1), OutlineEntry(1, "Chapter 8 Teams", 5)]
        self.assertEqual(
            [(s.number, s.end) for s in find_chapter_sections(chapter_titled, 9)], [(7, 4), (8, 9)]
        )
        self.assertEqual(find_chapter_sections([OutlineEntry(1, "Cover", 1)], 5), [])

    def test_pypdf_tools_read_outline_and_write_chapter(self) -> None:
        """Outline levels/pages round-trip; a chapter keeps its page count and inner bookmarks."""
        with tempfile.TemporaryDirectory() as tmp:
            book = Path(tmp) / "book.pdf"
            make_book(book, 13, OUTLINE)
            tools = PypdfTextbookTools()
            entries, total = tools.read_outline(book)
            self.assertEqual(total, 13)
            self.assertEqual([(e.level, e.title, e.page) for e in entries], OUTLINE)
            out = Path(tmp) / "ch1.pdf"
            tools.write_pages(PageRangeJob(book, 3, 5, out, [OutlineEntry(1, "1.1 Compare Methods", 2)]))
            reader = pypdf.PdfReader(str(out))
            self.assertEqual(len(reader.pages), 3)
            self.assertEqual([o.title for o in reader.outline], ["1.1 Compare Methods"])


class TextbookServiceTest(unittest.TestCase):
    """Scenarios 18c–18f."""

    def setUp(self) -> None:
        """Create DATA_DIR, database and a record-only course folder."""
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
        self.materials = self.course_dir / "01 Materials"
        (self.course_dir / "02 Handouts").mkdir(parents=True)
        make_book(self.materials / "Research Methods.pdf", 13, OUTLINE)
        make_book(self.materials / "Literature_Review" / "paper.pdf", 2, [])
        self._save_course([])

    def tearDown(self) -> None:
        """Dispose the engine and remove temporary files."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _save_course(self, lectures: list[Lecture], **extra: object) -> None:
        """Persist the test course.

        Args:
            lectures: Lecture rows to store.
            **extra: Additional Course fields.
        """
        course = Course(
            code=CODE,
            name="心理學研究法",
            source_dir=str(self.course_dir),
            study_dir=str(self.course_dir),
            profile=ProfileName.RECORD_ONLY,
            lectures=lectures,
        )
        with self.session_factory() as session:
            CourseRepository(session).save_course(replace(course, **extra))  # type: ignore[arg-type]
            session.commit()

    def _service(self, session: object) -> TextbookService:
        """Build the service on a session.

        Args:
            session: SQLAlchemy session.

        Returns:
            TextbookService bound to the course repository and pypdf tools.
        """
        return TextbookService(self.cfg, CourseRepository(session), PypdfTextbookTools())  # type: ignore[arg-type]

    def test_split_textbook_preview_apply_rerun_and_lectures(self) -> None:
        """Preview writes nothing; apply writes chapters + marker; chapters become lectures; rerun skips."""
        with self.session_factory() as session:
            svc = self._service(session)
            self.assertEqual(
                [t["relative_path"] for t in svc.list_textbooks(CODE)], ["01 Materials/Research Methods.pdf"]
            )
            preview = svc.split_textbook(CODE, "01 Materials/Research Methods.pdf")
            self.assertEqual([c["status"] for c in preview["chapters"]], ["create"] * 3)
            self.assertFalse((self.materials / "Research Methods").exists())
            applied = svc.split_textbook(CODE, "01 Materials/Research Methods.pdf", dry_run=False)
            out = self.materials / "Research Methods"
            self.assertEqual(
                sorted(p.name for p in out.glob("*.pdf")),
                [c["filename"] for c in applied["chapters"]],
            )
            self.assertTrue((out / ".textbook.json").is_file())
            self.assertTrue((self.materials / "Research Methods.pdf").is_file())
            course = CourseRepository(session).get_course(CODE)
            assert course is not None
            self.assertEqual([lec.no for lec in course.lectures], [1, 2, 3])
            self.assertTrue(
                all(lec.relative_path.startswith("01 Materials/Research Methods/") for lec in course.lectures)
            )
            again = svc.split_textbook(CODE, "01 Materials/Research Methods.pdf", dry_run=False)
            self.assertEqual([c["status"] for c in again["chapters"]], ["exists"] * 3)
            make_book(self.materials / "no-outline.pdf", 3, [])
            with self.assertRaisesRegex(ValueError, "找不到章節書籤"):
                svc.split_textbook(CODE, "01 Materials/no-outline.pdf")

    def test_relocate_handouts_keeps_lecture_numbers_and_sources(self) -> None:
        """Chapter PDFs move from 02 Handouts; numbers, hashes and source ids stay; conflicts stop."""
        handouts = self.course_dir / "02 Handouts"
        for name in ("Ch01-Intro.pdf", "Ch13-Tests.pdf"):
            make_book(handouts / name, 1, [])
        lectures = [
            Lecture(
                no=1,
                topic="Intro",
                filename="Ch01-Intro.pdf",
                sha256="a",
                source_id="src-1",
                upload_status="uploaded",
                category="02 Handouts",
                relative_path="02 Handouts/Ch01-Intro.pdf",
            ),
            Lecture(
                no=13,
                topic="Tests",
                filename="Ch13-Tests.pdf",
                sha256="b",
                source_id="src-13",
                upload_status="uploaded",
                category="02 Handouts",
                relative_path="02 Handouts/Ch13-Tests.pdf",
            ),
        ]
        self._save_course(lectures)
        with self.session_factory() as session:
            svc = self._service(session)
            preview = svc.relocate_handouts(CODE, "Career Counseling")
            self.assertEqual([m["filename"] for m in preview["moves"]], ["Ch01-Intro.pdf", "Ch13-Tests.pdf"])
            self.assertTrue((handouts / "Ch01-Intro.pdf").is_file())
            svc.relocate_handouts(CODE, "Career Counseling", dry_run=False)
            dest = self.materials / "Career Counseling"
            self.assertTrue((dest / "Ch13-Tests.pdf").is_file())
            self.assertTrue((dest / ".textbook.json").is_file())
            self.assertFalse(any(handouts.glob("*.pdf")))
            course = CourseRepository(session).get_course(CODE)
            assert course is not None
            got = [
                (lec.no, lec.sha256, lec.source_id, lec.category, lec.relative_path)
                for lec in course.lectures
            ]
            self.assertEqual(
                got,
                [
                    (1, "a", "src-1", "01 Materials", "01 Materials/Career Counseling/Ch01-Intro.pdf"),
                    (13, "b", "src-13", "01 Materials", "01 Materials/Career Counseling/Ch13-Tests.pdf"),
                ],
            )
            self.assertEqual(svc.relocate_handouts(CODE, "Career Counseling")["moves"], [])
            make_book(handouts / "Ch01-Intro.pdf", 1, [])
            self._save_course(
                [replace(lectures[0], relative_path="02 Handouts/Ch01-Intro.pdf")],
                study_dir=str(self.course_dir),
            )
            with self.assertRaisesRegex(ValueError, "已存在"):
                svc.relocate_handouts(CODE, "Career Counseling", dry_run=False)

    def test_material_sources_exclude_marked_chapter_folders(self) -> None:
        """Whole-course material upload skips split chapter folders but keeps the full book and papers."""
        with self.session_factory() as session:
            self._service(session).split_textbook(CODE, "01 Materials/Research Methods.pdf", dry_run=False)
            course = CourseRepository(session).get_course(CODE)
        assert course is not None
        course = replace(course, generation_options=GenerationOptions(materials_as_source=True))
        names = sorted(p.relative_to(self.materials).as_posix() for p in list_material_source_pdfs(course))
        self.assertEqual(names, ["Literature_Review/paper.pdf", "Research Methods.pdf"])

    def test_textbook_entrypoints_http_mcp_and_web(self) -> None:
        """HTTP preview/apply, MCP confirm guard, and web menu wiring."""
        client = TestClient(create_app(config=self.cfg))
        listed = client.get(f"/api/courses/{CODE}/textbooks")
        self.assertEqual(listed.status_code, 200, listed.text)
        body = {"relative_path": "01 Materials/Research Methods.pdf"}
        preview = client.post(f"/api/courses/{CODE}/textbooks/split", json=body)
        self.assertEqual((preview.status_code, preview.json()["dry_run"]), (200, True))
        bad = client.post(f"/api/courses/{CODE}/textbooks/split", json={"relative_path": "../../x.pdf"})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(client.get("/api/courses/NOPE/textbooks").status_code, 404)
        reloc = client.post(f"/api/courses/{CODE}/textbooks/relocate-handouts", json={"book_folder": "Book"})
        self.assertEqual(reloc.status_code, 200, reloc.text)

        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        self.assertEqual(len(json.loads(tools["list_textbooks"].fn(CODE))["textbooks"]), 1)
        refused = json.loads(tools["split_textbook"].fn(CODE, body["relative_path"], dry_run=False))
        self.assertFalse(refused["confirmed"])
        self.assertFalse((self.materials / "Research Methods").exists())
        self.assertFalse(json.loads(tools["relocate_handouts_to_textbook"].fn(CODE, "Book"))["confirmed"])
        js = (STATIC / "studio-textbook.js").read_text(encoding="utf-8")
        self.assertIn("/textbooks/split", js)
        self.assertIn("/textbooks/relocate-handouts", js)
        self.assertIn("openTextbookSplitFlow", (STATIC / "studio-batch.js").read_text(encoding="utf-8"))
        self.assertIn("studio-textbook.js", (STATIC / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

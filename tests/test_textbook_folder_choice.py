"""SPEC-025 R3: with two textbook folders in one course, the user chooses where a whole book splits."""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

import pypdf
from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.adapters.pdf_textbook import PypdfTextbookTools
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course, ProfileName
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.textbook_split import TextbookService

logger = logging.getLogger(__name__)

CODE = "115-1_CP30210"
BOOK = "01 Materials/Research Methods.pdf"
STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
OUTLINE = [
    (1, "Part I", 2),
    (2, "1 Introduction to Scientific Research", 2),
    (2, "2 Research Approaches", 5),
    (2, "3 Ethics", 8),
]


def make_pdf(path: Path, pages: int, outline: list[tuple[int, str, int]]) -> None:
    """Write a blank PDF with optional nested bookmarks.

    Args:
        path: Destination file.
        pages: Page count (also makes contents distinct).
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


class FolderChoiceTest(unittest.TestCase):
    """Two marked chapter folders: preview offers both, applying needs an explicit, valid choice."""

    def setUp(self) -> None:
        """Create a course with a whole book and two marked chapter folders (A matches, B does not)."""
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
        course_dir = self.cfg.study_root_dir / "115-1" / "CP__30210-心理學研究法"
        self.materials = course_dir / "01 Materials"
        (course_dir / "02 Handouts").mkdir(parents=True)
        make_pdf(self.materials / "Research Methods.pdf", 10, OUTLINE)
        for folder, name, pages in (
            ("Book A", "Ch01-Introduction-to-Scientific-Research.pdf", 3),
            ("Book B", "Ch01-Other.pdf", 4),
        ):
            make_pdf(self.materials / folder / name, pages, [])
            (self.materials / folder / ".textbook.json").write_text(
                json.dumps({"chapters": [name]}), encoding="utf-8"
            )
        course = Course(
            code=CODE,
            name="心理學研究法",
            source_dir=str(course_dir),
            study_dir=str(course_dir),
            profile=ProfileName.RECORD_ONLY,
        )
        with self.session_factory() as session:
            CourseRepository(session).save_course(course)

    def tearDown(self) -> None:
        """Dispose the engine and remove temporary files."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _split(self, **kwargs: object) -> dict[str, object]:
        """Call `split_textbook` on a fresh session.

        Args:
            **kwargs: `dry_run` and `target_folder`.

        Returns:
            Service result.
        """
        with self.session_factory() as session:
            svc = TextbookService(self.cfg, CourseRepository(session), PypdfTextbookTools())  # type: ignore[arg-type]
            return svc.split_textbook(CODE, BOOK, **kwargs)  # type: ignore[arg-type]

    def test_preview_offers_both_folders_and_suggests_the_matching_one(self) -> None:
        """Dry run lists both folders, flags that a choice is needed, and defaults to Book A."""
        preview = self._split()
        self.assertTrue(preview["needs_folder_choice"])
        choices = preview["folder_choices"]
        self.assertEqual([c["path"] for c in choices], ["01 Materials/Book A", "01 Materials/Book B"])  # type: ignore[index]
        self.assertEqual(preview["output_dir"], "01 Materials/Book A")
        self.assertEqual([c["status"] for c in preview["chapters"]], ["exists", "create", "create"])  # type: ignore[index]

    def test_apply_without_choice_writes_nothing(self) -> None:
        """Splitting for real without a folder is refused."""
        with self.assertRaises(ValueError):
            self._split(dry_run=False)
        self.assertEqual(
            sorted(p.name for p in (self.materials / "Book A").glob("*.pdf")),
            ["Ch01-Introduction-to-Scientific-Research.pdf"],
        )

    def test_apply_with_choice_fills_only_that_folder(self) -> None:
        """With target_folder the chapters land in Book A and Book B stays untouched."""
        result = self._split(dry_run=False, target_folder="Book A")
        self.assertEqual(result["output_dir"], "01 Materials/Book A")
        self.assertEqual(len(list((self.materials / "Book A").glob("Ch*.pdf"))), 3)
        self.assertEqual([p.name for p in (self.materials / "Book B").glob("*.pdf")], ["Ch01-Other.pdf"])

    def test_choice_must_be_one_of_the_offered_folders(self) -> None:
        """Unknown or escaping folder names are rejected."""
        for bad in ("Nope", "../02 Handouts", "Book A/sub"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self._split(dry_run=True, target_folder=bad)

    def test_entrypoints(self) -> None:
        """HTTP takes target_folder (422 without it), MCP has a confirm-guarded tool, web shows a picker."""
        client = TestClient(create_app(config=self.cfg))
        url = f"/api/courses/{CODE}/textbooks/split"
        self.assertEqual(client.post(url, json={"relative_path": BOOK, "dry_run": False}).status_code, 422)
        ok = client.post(url, json={"relative_path": BOOK, "dry_run": True, "target_folder": "Book B"})
        self.assertEqual((ok.status_code, ok.json()["output_dir"]), (200, "01 Materials/Book B"))
        tools = build_mcp_server(config=self.cfg)._tool_manager._tools  # type: ignore[attr-defined]
        refused = json.loads(tools["split_textbook_into_folder"].fn(CODE, BOOK, "Book A"))
        self.assertFalse(refused["confirmed"])
        self.assertEqual(len(list((self.materials / "Book A").glob("Ch*.pdf"))), 1)
        done = json.loads(tools["split_textbook_into_folder"].fn(CODE, BOOK, "Book A", confirm=True))
        self.assertEqual((done["confirmed"], done["output_dir"]), (True, "01 Materials/Book A"))
        self.assertEqual(len(list((self.materials / "Book A").glob("Ch*.pdf"))), 3)
        js = (STATIC / "studio-textbook.js").read_text(encoding="utf-8")
        self.assertIn("folder_choices", js)
        self.assertIn("target_folder", js)


if __name__ == "__main__":
    unittest.main()

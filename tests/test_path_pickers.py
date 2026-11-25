"""Project rule (2026-11-25): every path on the web page is chosen from a list, never typed."""

from __future__ import annotations

import logging
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.entrypoints.api import create_app

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parents[1] / "src" / "notebooklm_batch_studio" / "entrypoints" / "static"
PATH_WORDS = re.compile(r"路徑|資料夾|子資料夾|[Pp]ath|[Ss]ubfolder")
# Allowed: naming a NEW folder after choosing「＋ 新增資料夾…」, and fields that only *mention* folders
# (course display name says the folder stays; the add-course name defaults from the picked folder).
ALLOWED = ("新資料夾名稱", "的新課程名稱", 'id="addCourseName"')


def _read(name: str) -> str:
    """Read one static web file.

    Args:
        name: File name.

    Returns:
        File contents.
    """
    return (STATIC / name).read_text(encoding="utf-8")


class PathPickerRuleTest(unittest.TestCase):
    """Typed path inputs are replaced by pickers; a guard keeps new ones out."""

    def test_no_typed_path_inputs_or_prompts_anywhere(self) -> None:
        """No <input>/<textarea> or window.prompt asks the user to type a path or folder."""
        offenders: list[str] = []
        for page in sorted(STATIC.glob("*.js")) + [STATIC / "index.html"]:
            text = page.read_text(encoding="utf-8")
            for tag in re.findall(r"<(?:input|textarea)\b[^>]*>", text):
                if "hidden" not in tag and PATH_WORDS.search(tag) and not any(x in tag for x in ALLOWED):
                    offenders.append(f"{page.name}: {tag[:90]}")
            for prompt in re.findall(r"prompt\(\s*[`'\"]([^`'\"]*)", text):
                if PATH_WORDS.search(prompt) and not any(x in prompt for x in ALLOWED):
                    offenders.append(f"{page.name}: prompt {prompt[:60]}")
        self.assertEqual(offenders, [])

    def test_pickers_are_selects_and_wired(self) -> None:
        """Chapter PDF, literature subfolder, archive-menu subfolder and textbook folder use selects."""
        html = _read("index.html")
        self.assertRegex(html, r'<select id="ngPdfPath"')
        self.assertRegex(html, r'<select id="litSubfolderInput"')
        self.assertIn("studio-pickers.js", html)
        self.assertRegex(_read("studio-literature-rows.js"), r"<select[^>]*data-lit-menu-sub")
        pickers = _read("studio-pickers.js")
        for needle in ("/subfolders?category=", "＋ 新增資料夾…", "function askPick"):
            self.assertIn(needle, pickers)
        textbook = _read("studio-textbook.js")
        self.assertIn("askPick(", textbook)
        self.assertNotIn("window.prompt", textbook)


class SubfoldersApiTest(unittest.TestCase):
    """`GET /api/courses/{code}/subfolders` lists existing category subfolders safely."""

    def setUp(self) -> None:
        """Create a course with two materials subfolders."""
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
        course_dir = self.cfg.study_root_dir / "115-1" / "CP__30210-心理學研究法"
        for sub in ("Research Methods", "Literature_Review", ".hidden"):
            (course_dir / "01 Materials" / sub).mkdir(parents=True)
        (course_dir / "01 Materials" / "book.pdf").write_bytes(b"%PDF")
        with make_session_factory(self.engine)() as session:
            CourseRepository(session).save_course(
                Course(
                    code="115-1_CP30210",
                    name="心理學研究法",
                    source_dir=str(course_dir),
                    study_dir=str(course_dir),
                )
            )
            session.commit()
        self.client = TestClient(create_app(config=self.cfg))

    def tearDown(self) -> None:
        """Dispose the engine and remove temporary files."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_lists_visible_subfolders_and_rejects_bad_input(self) -> None:
        """Visible folders only, sorted; unknown course 404; traversal 400; missing category empty."""
        url = "/api/courses/115-1_CP30210/subfolders"
        res = self.client.get(url, params={"category": "01 Materials"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["subfolders"], ["Literature_Review", "Research Methods"])
        self.assertEqual(self.client.get(url, params={"category": "05 Assignments"}).json()["subfolders"], [])
        self.assertEqual(self.client.get(url, params={"category": "../.."}).status_code, 400)
        self.assertEqual(
            self.client.get("/api/courses/NOPE/subfolders", params={"category": "01 Materials"}).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()

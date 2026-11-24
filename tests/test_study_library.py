"""Tests for StudyLibraryService, school folder scanning, and term-scoped registration (SPEC-014 §5.5)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import CourseStatus, ProfileName
from notebooklm_batch_studio.services.course_parser import scan_course_directory
from notebooklm_batch_studio.services.study_library import StudyLibraryService


class StudyLibraryTests(unittest.TestCase):
    """BDD Scenario 9: scan study/<term>/, distinguish others, register record-only without jobs."""

    def setUp(self) -> None:
        """Create an isolated temp DATA_DIR and SQLite database."""
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        data_dir = root / "data"
        self.cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        self.cfg.ensure_data_dirs()
        self.engine = create_db_engine(self.cfg.database_url)
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)

    def tearDown(self) -> None:
        """Dispose DB engine and clean up temporary directory."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _make_course_tree(self, term: str, folder: str, pdfs: list[str]) -> Path:
        """Create a study/<term>/<folder>/02 Handouts tree with sample PDFs."""
        cdir = self.cfg.study_root_dir / term / folder
        handouts = cdir / "02 Handouts"
        handouts.mkdir(parents=True, exist_ok=True)
        for idx, name in enumerate(pdfs, start=1):
            (handouts / name).write_bytes(f"%PDF-1.4\n{term}:{folder}:{idx}".encode())
        return cdir

    def test_scan_distinguishes_courses_and_others(self) -> None:
        """Scenario 9: scan() separates school-format courses from non-course folders and files."""
        self._make_course_tree("113-1", "CP__30000-團體諮商", ["01_ch1.pdf"])
        self._make_course_tree("115-1", "CP__30000-團體諮商", ["01_w1.pdf", "02_w2.pdf"])
        t115 = self.cfg.study_root_dir / "115-1"
        (t115 / "Course Outline").mkdir(parents=True, exist_ok=True)
        (t115 / "專題").mkdir(parents=True, exist_ok=True)
        (t115 / "Holland學習單.docx").write_text("doc", encoding="utf-8")

        with self.session_factory() as session:
            svc = StudyLibraryService(self.cfg, CourseRepository(session))
            terms = svc.scan()

        self.assertEqual([t.term for t in terms], ["113-1", "115-1"])
        by_term = {t.term: t for t in terms}
        self.assertEqual([c.code for c in by_term["115-1"].courses], ["115-1_CP30000"])
        self.assertEqual(by_term["115-1"].courses[0].lecture_count, 2)
        self.assertEqual(by_term["115-1"].others, ["Course Outline", "Holland學習單.docx", "專題"])

    def test_register_creates_record_only_archived_and_skips_duplicates(self) -> None:
        """Scenario 9: register() marks RECORD_ONLY + ARCHIVED, creates zero jobs, separates retakes."""
        c113 = self._make_course_tree("113-1", "CP__30000-團體諮商", ["01_w1.pdf"])
        c115 = self._make_course_tree("115-1", "CP__30000-團體諮商", ["01_w1.pdf"])

        with self.session_factory() as session:
            c_repo = CourseRepository(session)
            q_repo = QueueRepository(session)
            svc = StudyLibraryService(self.cfg, c_repo)
            out = svc.register(["113-1_CP30000", "115-1_CP30000"], archive=True)
            self.assertEqual(len(out), 2)

            course_113 = c_repo.get_course("113-1_CP30000")
            course_115 = c_repo.get_course("115-1_CP30000")
            assert course_113 is not None and course_115 is not None
            self.assertEqual(course_113.profile, ProfileName.RECORD_ONLY)
            self.assertEqual(course_113.status, CourseStatus.ARCHIVED)
            self.assertEqual(course_113.term, "113-1")
            self.assertEqual(course_113.study_dir, str(c113.resolve()))
            self.assertNotEqual(course_113.study_dir, course_115.study_dir)
            self.assertEqual(course_115.study_dir, str(c115.resolve()))
            self.assertEqual(q_repo.list_jobs(course_code="113-1_CP30000"), [])

            dup = svc.register(["113-1_CP30000"])
            self.assertEqual(dup[0]["skipped"], "already registered")

    def test_register_folder_nonstandard_directory(self) -> None:
        """Scenario 9: manual registration turns '專題' into 115-1_PROJ1151 with name '專題'."""
        proj = self._make_course_tree("115-1", "專題", ["01_proposal.pdf"])

        with self.session_factory() as session:
            c_repo = CourseRepository(session)
            svc = StudyLibraryService(self.cfg, c_repo)
            res = svc.register_folder("115-1", "專題", "PROJ1151")
            self.assertEqual(res["code"], "115-1_PROJ1151")
            self.assertEqual(res["name"], "專題")

            saved = c_repo.get_course("115-1_PROJ1151")
            assert saved is not None
            self.assertEqual(saved.course_no, "PROJ1151")
            self.assertEqual(saved.profile, ProfileName.RECORD_ONLY)
            self.assertEqual(saved.status, CourseStatus.ARCHIVED)
            self.assertEqual(saved.study_dir, str(proj.resolve()))

            scanned = {t.term: t for t in svc.scan()}["115-1"]
            self.assertEqual([c.code for c in scanned.courses], ["115-1_PROJ1151"])
            self.assertTrue(scanned.courses[0].registered)

    def test_real_school_folder_names_yield_distinct_codes(self) -> None:
        """Real school CP__/YY__ names in a temp term dir resolve without CP collisions."""
        folders = [
            "CP__30000-團體諮商",
            "CP__30210-心理學研究法",
            "CP__31000-生涯諮商與實務",
            "YY__5061AA-體育 (三)_超慢跑 AA",
        ]
        paths = [self._make_course_tree("115-1", folder, ["01_intro.pdf"]) for folder in folders]

        scanned_courses = [scan_course_directory(p) for p in paths]
        self.assertEqual(
            [c.code for c in scanned_courses],
            ["115-1_CP30000", "115-1_CP30210", "115-1_CP31000", "115-1_YY5061AA"],
        )
        self.assertEqual(scanned_courses[3].name, "體育 (三)_超慢跑 AA")
        self.assertEqual(scanned_courses[3].course_no, "YY5061AA")

        with self.session_factory() as session:
            terms = StudyLibraryService(self.cfg, CourseRepository(session)).scan()
        self.assertEqual(
            [c.code for c in terms[0].courses],
            ["115-1_CP30000", "115-1_CP30210", "115-1_CP31000", "115-1_YY5061AA"],
        )


if __name__ == "__main__":
    unittest.main()

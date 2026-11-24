"""Tests verifying retirement of legacy input/courses and output/courses layouts (SPEC-014 §5.4)."""

from __future__ import annotations

import base64
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.services.folder_browser import browse_folders
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.study_service import StudyTrackerService


class OldLayoutRetiredTests(unittest.TestCase):
    """BDD scenarios ensuring flashcards, uploads, folder picker, and services avoid legacy layout."""

    def setUp(self) -> None:
        """Create an isolated temporary environment and SQLite database."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name).resolve()
        self.data_dir = self.root / "data"
        self.cfg = AppConfig(
            data_dir=self.data_dir,
            database_url=f"sqlite:///{self.data_dir / 'db' / 'app.db'}",
            log_to_file=False,
        )
        self.cfg.ensure_data_dirs()
        self.engine = create_db_engine(self.cfg.database_url)
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)

    def tearDown(self) -> None:
        """Dispose database engine and remove temp workspace."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_flashcards_never_read_another_course(self) -> None:
        """Scenario 8a: flashcards resolve strictly to the requested course's study_dir."""
        dir_a = self.cfg.study_root_dir / "115-1" / "CP__30000-團體諮商"
        dir_b = self.cfg.study_root_dir / "115-1" / "CP__31000-生涯諮商與實務"
        fc_a = dir_a / "03 Notes" / "NotebookLM" / "03_x" / "flashcards.json"
        fc_b = dir_b / "03 Notes" / "NotebookLM" / "03_x" / "flashcards.json"
        fc_b.parent.mkdir(parents=True, exist_ok=True)
        fc_b.write_text(json.dumps({"cards": [{"front": "B-front", "back": "B-back"}]}), encoding="utf-8")

        with self.session_factory() as session:
            course_repo = CourseRepository(session)
            course_repo.save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir=str(dir_a),
                    study_dir=str(dir_a),
                    course_no="CP30000",
                    term="115-1",
                )
            )
            course_repo.save_course(
                Course(
                    code="115-1_CP31000",
                    name="生涯諮商與實務",
                    source_dir=str(dir_b),
                    study_dir=str(dir_b),
                    course_no="CP31000",
                    term="115-1",
                )
            )
            study = StudyTrackerService(StudyRepository(session), config=self.cfg, course_repo=course_repo)
            self.assertEqual(study.get_lecture_flashcards("115-1_CP30000", 3), [])

            fc_a.parent.mkdir(parents=True, exist_ok=True)
            fc_a.write_text(json.dumps({"cards": [{"front": "A-front", "back": "A-back"}]}), encoding="utf-8")
            self.assertEqual(study.get_lecture_flashcards("115-1_CP30000", 3)[0]["front"], "A-front")

    def test_uploads_land_in_handouts(self) -> None:
        """Scenario 8b: uploaded base64 PDFs land under <study_dir>/02 Handouts/_uploaded/."""
        course_dir = self.cfg.study_root_dir / "115-1" / "CP__30000-團體諮商"
        (course_dir / "02 Handouts").mkdir(parents=True, exist_ok=True)
        b64 = base64.b64encode(b"%PDF-1.4\nupload").decode("ascii")

        with self.session_factory() as session:
            c_repo = CourseRepository(session)
            c_repo.save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir=str(course_dir),
                    study_dir=str(course_dir),
                    course_no="CP30000",
                    term="115-1",
                )
            )
            svc = BatchStudioService(c_repo, QueueRepository(session), mock.MagicMock(), self.cfg)
            out = svc._save_uploaded_base64_pdf("115-1_CP30000", "x.pdf", b64)
            self.assertTrue(out.is_relative_to(course_dir / "02 Handouts" / "_uploaded"))
            self.assertFalse(self.cfg.courses_input_dir.exists())

    def test_folder_browser_shortcuts(self) -> None:
        """Scenario 8c: folder picker shortcuts start with study_root_dir and scratch_dir."""
        data = browse_folders(None, self.cfg, home=self.root)
        paths = [entry["path"] for entry in data["folders"][:2]]
        self.assertEqual(paths, [str(self.cfg.study_root_dir.resolve()), str(self.cfg.scratch_dir.resolve())])

    def test_no_new_writes_to_old_layout(self) -> None:
        """Scenario 8d: no source file outside migration/consolidation joins paths under old layout."""
        writers = [
            str(f)
            for f in Path("src/notebooklm_batch_studio").rglob("*.py")
            if re.search(r"courses_(input|output)_dir\s*/", f.read_text(encoding="utf-8"))
        ]
        allowed = {
            "src/notebooklm_batch_studio/services/study_migration.py",
            "src/notebooklm_batch_studio/services/legacy_consolidation.py",
        }
        self.assertTrue(set(writers) <= allowed, writers)
        self.assertIn("src/notebooklm_batch_studio/services/study_migration.py", writers)


if __name__ == "__main__":
    unittest.main()

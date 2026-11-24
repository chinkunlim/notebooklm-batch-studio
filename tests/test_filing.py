"""Tests for FilingService generic scratch <-> study archiving and unfiling (SPEC-014 §5.5)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.domain.path_safety import PathSafetyError
from notebooklm_batch_studio.domain.study_layout import CategoryRole
from notebooklm_batch_studio.services.filing import FilingService, FilingTarget


class FilingServiceTests(unittest.TestCase):
    """BDD Scenario 10c: file from scratch to category, collision suffix, unfile, safety guard."""

    def setUp(self) -> None:
        """Create isolated temp DATA_DIR, SQLite database, and a registered study course."""
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
        self.study_dir = self.cfg.study_root_dir / "115-1" / "CP__30000-團體諮商"
        self.cfg.study_layout.ensure_tree(self.study_dir)
        with self.session_factory() as session:
            CourseRepository(session).save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir=str(self.study_dir.resolve()),
                    study_dir=str(self.study_dir.resolve()),
                    term="115-1",
                    course_no="CP30000",
                )
            )

    def tearDown(self) -> None:
        """Dispose DB engine and clean up temporary workspace."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_list_unfiled_and_file_into_category_with_collision_suffix(self) -> None:
        """Filing moves file to target subfolder, keeps scratch clean, adds -2/-3 on collision."""
        src = self.cfg.scratch_kind_dir("outputs") / "midterm.pdf"
        src.write_bytes(b"%PDF-1.4\nv1")
        src_dup = self.cfg.scratch_kind_dir("literature") / "midterm.pdf"
        src_dup.write_bytes(b"%PDF-1.4\nv2")

        with self.session_factory() as session:
            svc = FilingService(self.cfg, CourseRepository(session))
            all_unfiled = svc.list_unfiled()
            self.assertEqual(len(all_unfiled), 2)
            self.assertEqual([e["name"] for e in svc.list_unfiled("literature")], ["midterm.pdf"])

            dest1 = svc.file(
                src,
                FilingTarget(course_code="115-1_CP30000", role=CategoryRole.ASSIGNMENTS, subfolder="期中"),
            )
            self.assertFalse(src.exists())
            expected_dir = (self.study_dir / "05 Assignments" / "期中").resolve()
            self.assertEqual(dest1.resolve(), expected_dir / "midterm.pdf")
            self.assertEqual(dest1.read_bytes(), b"%PDF-1.4\nv1")

            dest2 = svc.file(
                src_dup,
                FilingTarget(course_code="115-1_CP30000", role=CategoryRole.ASSIGNMENTS, subfolder="期中"),
            )
            self.assertEqual(dest2.name, "midterm-2.pdf")
            self.assertEqual(dest1.read_bytes(), b"%PDF-1.4\nv1")
            self.assertEqual(dest2.read_bytes(), b"%PDF-1.4\nv2")

    def test_notes_root_protected_and_unfile_moves_to_scratch_unarchived(self) -> None:
        """NOTES role requires a subfolder; unfile moves file to scratch/unarchived/<code>/."""
        note_src = self.cfg.scratch_kind_dir("notes") / "summary.md"
        note_src.write_text("# AI summary", encoding="utf-8")

        with self.session_factory() as session:
            svc = FilingService(self.cfg, CourseRepository(session))
            with self.assertRaises(ValueError):
                svc.file(note_src, FilingTarget(course_code="115-1_CP30000", role=CategoryRole.NOTES))

            filed = svc.file(
                note_src,
                FilingTarget(course_code="115-1_CP30000", role=CategoryRole.NOTES, subfolder="NotebookLM"),
            )
            self.assertTrue(filed.is_file())

            unfiled = svc.unfile(filed)
            self.assertFalse(filed.exists())
            self.assertEqual(
                unfiled.resolve(),
                (self.cfg.scratch_kind_dir("unarchived") / "115-1_CP30000" / "summary.md").resolve(),
            )
            self.assertEqual(unfiled.read_text(encoding="utf-8"), "# AI summary")

    def test_outside_paths_rejected_by_path_safety(self) -> None:
        """Filing or unfiling paths outside scratch_dir and registered study dirs raises PathSafetyError."""
        outside = Path(self.tmpdir.name) / "etc_hosts.txt"
        outside.write_text("127.0.0.1 localhost", encoding="utf-8")

        with self.session_factory() as session:
            svc = FilingService(self.cfg, CourseRepository(session))
            with self.assertRaises(PathSafetyError):
                svc.file(
                    outside,
                    FilingTarget(course_code="115-1_CP30000", role=CategoryRole.MATERIALS),
                )
            with self.assertRaises(PathSafetyError):
                svc.unfile(outside)


if __name__ == "__main__":
    unittest.main()

"""Tests for course status, course_no, record-only profile, and literature defaults (SPEC-014 §5.4)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.models import LiteratureItemRecord
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.domain.models import Course, CourseStatus, Lecture, ProfileName
from notebooklm_batch_studio.domain.study_layout import DEFAULT_LAYOUT, CategoryRole
from notebooklm_batch_studio.services.job_planner import generate_jobs_for_course


class CourseLifecycleDbTests(unittest.TestCase):
    """BDD scenarios for DB course status/course_no, record-only profile, and legacy literature alias."""

    def setUp(self) -> None:
        """Create an isolated SQLite database per test."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_url = f"sqlite:///{Path(self.tmpdir.name) / 'app.db'}"
        self.engine = create_db_engine(self.db_url)
        Base.metadata.create_all(self.engine)
        self.session_factory = make_session_factory(self.engine)

    def tearDown(self) -> None:
        """Dispose DB engine and clean up temporary folder."""
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_course_status_and_course_no_round_trip_and_filter(self) -> None:
        """Scenario 7a: status and course_no persist and list_courses filters by status."""
        with self.session_factory() as session:
            repo = CourseRepository(session)
            repo.save_course(
                Course(
                    code="115-1_CP30000",
                    name="團體諮商",
                    source_dir="/tmp/c1",
                    term="115-1",
                    subject="CP__30000-團體諮商",
                    course_no="CP30000",
                    status=CourseStatus.ACTIVE,
                )
            )
            repo.save_course(
                Course(
                    code="113-1_PSY101",
                    name="普通心理學",
                    source_dir="/tmp/c2",
                    term="113-1",
                    subject="PSY__101-普通心理學",
                    course_no="PSY101",
                    profile=ProfileName.RECORD_ONLY,
                    status=CourseStatus.ARCHIVED,
                )
            )

            loaded = repo.get_course("113-1_PSY101")
            assert loaded is not None
            self.assertEqual(loaded.status, CourseStatus.ARCHIVED)
            self.assertEqual(loaded.course_no, "PSY101")
            self.assertEqual(loaded.profile, ProfileName.RECORD_ONLY)

            archived = repo.list_courses(status=CourseStatus.ARCHIVED)
            self.assertEqual([c.code for c in archived], ["113-1_PSY101"])
            active = repo.list_courses(status=CourseStatus.ACTIVE)
            self.assertEqual([c.code for c in active], ["115-1_CP30000"])
            self.assertEqual(len(repo.list_courses()), 2)

    def test_record_only_profile_generates_no_jobs(self) -> None:
        """Scenario 7b: record-only courses produce zero scheduled artifact jobs."""
        course = Course(
            code="113-1_PSY101",
            name="普通心理學",
            source_dir="/tmp/c2",
            profile=ProfileName.RECORD_ONLY,
            lectures=[Lecture(no=1, topic="導論", filename="01.pdf", sha256="abc")],
        )
        self.assertEqual(generate_jobs_for_course(course), [])

    def test_legacy_literature_singular_category_maps_to_materials_role(self) -> None:
        """Scenario 7c: existing DB row with '01 Material' resolves to CategoryRole.MATERIALS."""
        with self.session_factory() as session:
            session.add(
                LiteratureItemRecord(
                    key="LegacyPaper_2022",
                    position=0,
                    input_text="10.1000/legacy",
                    target_category="01 Material",
                )
            )
            session.commit()

            item = LiteratureRepository(session).get_item("LegacyPaper_2022")
            assert item is not None
            self.assertEqual(item.target_category, "01 Material")
            self.assertEqual(DEFAULT_LAYOUT.role_of(item.target_category), CategoryRole.MATERIALS)


if __name__ == "__main__":
    unittest.main()

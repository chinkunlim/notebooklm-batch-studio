"""Regression test: re-registering a course must keep Gemini Notebook source ids of unchanged PDFs.

Without this, `batch` on an already-uploaded course (or the folder watcher re-registering
on every new PDF) re-uploads every lecture and duplicates sources in the notebook.
"""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.domain.models import Course, Lecture


def _course(lectures: list[Lecture]) -> Course:
    """Build a course as `scan_course_directory` would (no notebook / source ids).

    Args:
        lectures: Lectures to include.

    Returns:
        Course entity.
    """
    return Course(code="PSY", name="心理學研究法", source_dir="/x", lectures=lectures)


class ReRegistrationTest(unittest.TestCase):
    """save_course must merge, not wipe, existing upload state."""

    def setUp(self) -> None:
        """Save a course whose two lectures are already uploaded."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine)()
        self.repo = CourseRepository(self.session)
        self.repo.save_course(
            _course(
                [
                    Lecture(no=1, topic="a", filename="01.pdf", sha256="h1"),
                    Lecture(no=2, topic="b", filename="02.pdf", sha256="h2"),
                ]
            )
        )
        self.repo.update_notebook_id("PSY", "nb-1")
        for no, src in ((1, "src-1"), (2, "src-2")):
            self.repo.update_lecture_upload_status("PSY", no, "ready", source_id=src)

    def tearDown(self) -> None:
        """Close the session."""
        self.session.close()

    def test_rescan_keeps_source_ids_of_unchanged_pdfs(self) -> None:
        """Same sha256 keeps source id and ready status; changed or new PDFs need upload."""
        self.repo.save_course(
            _course(
                [
                    Lecture(no=1, topic="a", filename="01.pdf", sha256="h1"),
                    Lecture(no=2, topic="b", filename="02.pdf", sha256="h2-edited"),
                    Lecture(no=3, topic="c", filename="03.pdf", sha256="h3"),
                ]
            )
        )
        course = self.repo.get_course("PSY")
        assert course is not None
        by_no = {lec.no: lec for lec in course.lectures}
        self.assertEqual(course.notebook_id, "nb-1")
        self.assertEqual((by_no[1].source_id, by_no[1].upload_status), ("src-1", "ready"))
        self.assertIsNone(by_no[2].source_id)
        self.assertIsNone(by_no[3].source_id)


if __name__ == "__main__":
    unittest.main()

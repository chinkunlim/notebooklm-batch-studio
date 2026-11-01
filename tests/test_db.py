"""Tests for the database adapter (in-memory SQLite, no files left behind)."""

from __future__ import annotations

import unittest

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory, session_scope
from notebooklm_batch_studio.domain.models import Course


class SessionScopeTest(unittest.TestCase):
    """Commit and rollback behaviour of `session_scope`."""

    def setUp(self) -> None:
        """Create a fresh in-memory database with all tables."""
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.factory = make_session_factory(engine)

    def test_add_and_read_back(self) -> None:
        """A course saved in one scope is readable in the next."""
        with session_scope(self.factory) as session:
            CourseRepository(session).save_course(Course(code="C1", name="課", source_dir="/x"))
        with session_scope(self.factory) as session:
            self.assertIsNotNone(CourseRepository(session).get_course("C1"))

    def test_error_rolls_back(self) -> None:
        """An exception inside `session_scope` before commit leaves the database unchanged."""
        with self.assertRaises(RuntimeError), session_scope(self.factory) as session:
            from notebooklm_batch_studio.adapters.db.models import CourseRecord

            session.add(CourseRecord(code="C2", name="課", source_dir="/x"))
            session.flush()
            raise RuntimeError("boom")
        with session_scope(self.factory) as session:
            self.assertIsNone(CourseRepository(session).get_course("C2"))


if __name__ == "__main__":
    unittest.main()

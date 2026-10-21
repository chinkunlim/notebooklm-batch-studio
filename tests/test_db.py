"""Tests for the database adapter (in-memory SQLite, no files left behind)."""

from __future__ import annotations

import unittest

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.repository import GreetingRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory, session_scope
from notebooklm_batch_studio.domain.models import GreetingResult


class GreetingRepositoryTest(unittest.TestCase):
    """Storing and reading greetings."""

    def setUp(self) -> None:
        """Create a fresh in-memory database with all tables."""
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.factory = make_session_factory(engine)

    def test_add_and_read_back(self) -> None:
        """A stored greeting comes back from `recent()`."""
        with session_scope(self.factory) as session:
            GreetingRepository(session).add("Ann", GreetingResult(message="Hello, Ann!", environment="test"))
        with session_scope(self.factory) as session:
            rows = GreetingRepository(session).recent(environment="test")
        self.assertEqual([r.message for r in rows], ["Hello, Ann!"])

    def test_error_rolls_back(self) -> None:
        """An exception inside `session_scope` leaves the database unchanged."""
        with self.assertRaises(RuntimeError), session_scope(self.factory) as session:
            GreetingRepository(session).add("Bob", GreetingResult(message="Hello, Bob!", environment="test"))
            raise RuntimeError("boom")
        with session_scope(self.factory) as session:
            self.assertEqual(GreetingRepository(session).recent(), [])


if __name__ == "__main__":
    unittest.main()

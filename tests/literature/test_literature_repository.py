"""Offline tests for `LiteratureRepository` (scenarios ported from literature-fetch tests/test_db.py).

literature-fetch stored items with `SqlItemStore`; this project uses the SQLAlchemy
`LiteratureRepository` over the shared app database, so the same scenarios run against it:
round trip with field fidelity and order, update/delete, key rename, and job lifecycle.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from notebooklm_batch_studio.adapters.db.base import Base  # noqa: E402
from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository  # noqa: E402
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory  # noqa: E402
from notebooklm_batch_studio.domain.literature.literature import Reference, ReferenceKind  # noqa: E402
from notebooklm_batch_studio.domain.literature.tracker import ItemStatus, JobState, TrackedItem  # noqa: E402

WEBB = TrackedItem(
    "Webb_2012",
    "Webb",
    Reference(
        "Webb_2012",
        "Webb",
        doi="10.1037/a0027600",
        title="Dealing with feeling",
        author="Webb",
        pdf_urls=("https://x/a.pdf",),
    ),
    "Webb, T. L. (2012).",
    ItemStatus.DOWNLOADED,
    file="Webb_2012.pdf",
    note="n",
    source="s",
    check="c",
)
LOST = TrackedItem("Unresolved_1", "unknown", None, "unknown", ItemStatus.NOT_FOUND)
BOOK = TrackedItem(
    "Beck_1976",
    "Beck",
    Reference("Beck_1976", "Beck", kind=ReferenceKind.BOOK, title="CT"),
    "Beck (1976).",
    ItemStatus.PENDING,
)


class LiteratureRepositoryTest(unittest.TestCase):
    """Items and jobs in the shared app database."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        engine = create_db_engine(f"sqlite:///{Path(self.tmp.name) / 'app.db'}")
        Base.metadata.create_all(engine)
        self.session = make_session_factory(engine)()
        self.repo = LiteratureRepository(self.session)

    def tearDown(self) -> None:
        self.session.close()
        self.tmp.cleanup()

    def test_round_trip_keeps_order_and_fields(self) -> None:
        for item in (WEBB, LOST, BOOK):
            self.repo.upsert_item(item)
        keys = [i.key for i in self.repo.list_items()]
        self.assertEqual(keys, ["Webb_2012", "Unresolved_1", "Beck_1976"])
        webb = self.repo.get_item("Webb_2012")
        assert webb is not None and webb.reference is not None
        self.assertEqual((webb.file, webb.note, webb.source, webb.check), ("Webb_2012.pdf", "n", "s", "c"))
        self.assertEqual(webb.reference.doi, "10.1037/a0027600")
        self.assertEqual(webb.reference.pdf_urls, ("https://x/a.pdf",))
        book = self.repo.get_item("Beck_1976")
        assert book is not None and book.reference is not None
        self.assertEqual(book.reference.kind, ReferenceKind.BOOK)
        lost = self.repo.get_item("Unresolved_1")
        assert lost is not None
        self.assertIsNone(lost.reference)
        self.assertIsNone(self.repo.get_item("missing"))

    def test_update_and_delete(self) -> None:
        self.repo.upsert_item(WEBB)
        self.repo.upsert_item(replace(WEBB, note="new"))
        updated = self.repo.get_item("Webb_2012")
        assert updated is not None
        self.assertEqual(updated.note, "new")
        self.assertEqual(len(self.repo.list_items()), 1)
        self.assertTrue(self.repo.delete_item("Webb_2012"))
        self.assertEqual(self.repo.list_items(), [])
        self.assertFalse(self.repo.delete_item("Webb_2012"))

    def test_rename_key_keeps_position(self) -> None:
        self.repo.upsert_item(WEBB)
        self.repo.upsert_item(LOST)
        self.repo.upsert_item(BOOK)
        found = TrackedItem(
            "Kosmyna_2025", "unknown", Reference("Kosmyna_2025", "k"), "K (2025).", ItemStatus.PENDING
        )
        self.repo.replace_key("Unresolved_1", found)
        self.assertEqual([i.key for i in self.repo.list_items()], ["Webb_2012", "Kosmyna_2025", "Beck_1976"])
        self.assertIsNone(self.repo.get_item("Unresolved_1"))

    def test_job_lifecycle(self) -> None:
        job = self.repo.start_job("download", total=3)
        self.repo.update_job(job.id, done=1, message="Webb_2012")
        latest = self.repo.latest_job()
        assert latest is not None
        self.assertEqual(
            (latest.id, latest.kind, latest.state, latest.total, latest.done, latest.message),
            (job.id, "download", JobState.RUNNING, 3, 1, "Webb_2012"),
        )
        self.repo.finish_job(job.id, JobState.DONE, "ok")
        latest = self.repo.latest_job()
        assert latest is not None
        self.assertEqual((latest.state, latest.message), (JobState.DONE, "ok"))
        self.assertIsNotNone(latest.finished_at)


if __name__ == "__main__":
    unittest.main()

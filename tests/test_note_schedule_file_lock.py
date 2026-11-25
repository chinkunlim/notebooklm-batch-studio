"""SPEC-025 R1: the note schedule file survives concurrent writers in separate processes (web + MCP)."""

from __future__ import annotations

import fcntl
import json
import logging
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import Course, Lecture
from notebooklm_batch_studio.entrypoints.api import create_app
from notebooklm_batch_studio.services.notes.note_scheduler import NoteScheduler, ScheduleBusyError

logger = logging.getLogger(__name__)

PER_PROCESS = 60


def _course(code: str) -> Course:
    """Build a course with `PER_PROCESS` lectures.

    Args:
        code: Course code (also the source folder name).

    Returns:
        Course.
    """
    lectures = [
        Lecture(no=n, topic=f"T{n}", filename=f"Ch{n:02d}.pdf", sha256=str(n))
        for n in range(1, PER_PROCESS + 1)
    ]
    return Course(code=code, name=code, source_dir=f"/tmp/{code}", lectures=lectures)


def _writer(path: str, code: str, start: multiprocessing.synchronize.Event) -> None:
    """Enqueue every lecture of one course, one call per lecture (a separate process).

    Args:
        path: Schedule file.
        code: Course code.
        start: Released when both writers are ready.
    """
    scheduler = NoteScheduler(Path(path), mock.Mock())
    course = _course(code)
    start.wait(10)
    for n in range(1, PER_PROCESS + 1):
        scheduler.enqueue_course(course, [n])


class FileLockTest(unittest.TestCase):
    """Two processes writing at once lose nothing; a stuck lock is reported, not waited on forever."""

    def setUp(self) -> None:
        """Create a temporary schedule path."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "state" / "note_schedule.json"

    def tearDown(self) -> None:
        """Remove temporary files."""
        self.tmpdir.cleanup()

    def test_two_processes_keep_every_item(self) -> None:
        """Web and MCP adding chapters at the same moment both land in the file."""
        ctx = multiprocessing.get_context("spawn")
        start = ctx.Event()
        procs = [ctx.Process(target=_writer, args=(str(self.path), code, start)) for code in ("A", "B")]
        for p in procs:
            p.start()
        start.set()
        for p in procs:
            p.join(60)
            self.assertEqual(p.exitcode, 0)
        items = json.loads(self.path.read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(items), 2 * PER_PROCESS)

    def test_held_lock_times_out_with_busy_error(self) -> None:
        """When another process holds the lock too long, a ScheduleBusyError is raised."""
        scheduler = NoteScheduler(self.path, mock.Mock())
        scheduler.lock_timeout = 0.3
        self.path.parent.mkdir(parents=True)
        fd = os.open(scheduler.lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            with self.assertRaises(ScheduleBusyError):
                scheduler.enqueue_course(_course("A"), [1])
        finally:
            os.close(fd)

    def test_http_returns_503_when_busy(self) -> None:
        """The web route answers 503 with a readable message instead of hanging."""
        data_dir = Path(self.tmpdir.name) / "data"
        cfg = AppConfig(
            data_dir=data_dir,
            database_url=f"sqlite:///{data_dir / 'db' / 'app.db'}",
            http_allowed_hosts=("127.0.0.1", "localhost", "testserver"),
        )
        cfg.ensure_data_dirs()
        app = create_app(config=cfg)
        busy = mock.Mock(status=mock.Mock(side_effect=ScheduleBusyError("筆記排程忙碌中，請稍後再試")))
        with mock.patch(
            "notebooklm_batch_studio.entrypoints.http.note_schedule._scheduler", return_value=busy
        ):
            res = TestClient(app).get("/api/notes/schedule")
        self.assertEqual(res.status_code, 503)
        self.assertIn("筆記排程忙碌中", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()

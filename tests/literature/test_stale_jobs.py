"""Tests for closing stale running literature jobs left by an interrupted process (Refs: ISSUE-054)."""

from __future__ import annotations

import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from notebooklm_batch_studio.adapters.db.base import Base
from notebooklm_batch_studio.adapters.db.literature_repository import LiteratureRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, make_session_factory
from notebooklm_batch_studio.adapters.literature.factory import AdapterLiteratureRuntime
from notebooklm_batch_studio.adapters.locks import RunLock
from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.literature.tracker import AlreadyRunningError, JobState
from notebooklm_batch_studio.services.literature.jobs import JobRunOptions, LiteratureJobRunner
from notebooklm_batch_studio.services.literature.manager import LiteratureManager


class StaleJobTest(unittest.TestCase):
    """A literature job left running by a process that was stopped (Ctrl-C, crash)."""

    def test_new_runner_closes_jobs_and_steps_left_by_a_stopped_process(self) -> None:
        """Creating a new runner closes leftover `running` jobs in `literature_jobs` as `failed`."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            cfg = AppConfig(
                app_env="test",
                log_to_file=False,
                data_dir=data_dir,
                database_url=f"sqlite:///{data_dir / 'app.db'}",
            )
            engine = create_db_engine(cfg.database_url)
            Base.metadata.create_all(engine)
            factory = make_session_factory(engine)
            with factory() as session:
                stale = LiteratureRepository(session).start_job("download", 1, "fetching")

            @contextmanager
            def _lit_scope() -> Iterator[LiteratureManager]:
                with factory() as session:
                    yield LiteratureManager(
                        cfg,
                        LiteratureRepository(session),
                        CourseRepository(session),
                        AdapterLiteratureRuntime(cfg),
                    )

            runner = LiteratureJobRunner(_lit_scope)
            with factory() as session:
                job = LiteratureRepository(session).latest_job()
            self.assertIsNotNone(job)
            assert job is not None
            self.assertEqual((job.id, job.state), (stale.id, JobState.FAILED))
            self.assertNotEqual(job.finished_at, "")
            self.assertEqual(runner.live_stage(), ("", ""))

    def test_worker_base_exception_marks_job_failed(self) -> None:
        """A BaseException such as KeyboardInterrupt inside worker cleanup still marks the job failed."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            cfg = AppConfig(
                app_env="test",
                log_to_file=False,
                data_dir=data_dir,
                database_url=f"sqlite:///{data_dir / 'app.db'}",
            )
            engine = create_db_engine(cfg.database_url)
            Base.metadata.create_all(engine)
            factory = make_session_factory(engine)

            @contextmanager
            def _lit_scope() -> Iterator[LiteratureManager]:
                with factory() as session:
                    yield LiteratureManager(
                        cfg,
                        LiteratureRepository(session),
                        CourseRepository(session),
                        AdapterLiteratureRuntime(cfg),
                    )

            runner = LiteratureJobRunner(_lit_scope)
            done_event = threading.Event()
            original_hook = threading.excepthook
            threading.excepthook = lambda _args: done_event.set()
            try:
                with patch.object(
                    LiteratureManager, "process_items", side_effect=KeyboardInterrupt("sigint")
                ):
                    job = runner.start("download", JobRunOptions(on_done=done_event.set))
                    self.assertTrue(done_event.wait(timeout=3.0))
                    if runner._thread is not None:
                        runner._thread.join(timeout=3.0)
            finally:
                threading.excepthook = original_hook

            with factory() as session:
                recorded = LiteratureRepository(session).latest_job()
            self.assertIsNotNone(recorded)
            assert recorded is not None
            self.assertEqual((recorded.id, recorded.state), (job.id, JobState.FAILED))
            self.assertNotEqual(recorded.finished_at, "")

    def test_second_runner_does_not_close_a_job_owned_by_a_live_runner(self) -> None:
        """A second runner starting while another process runs a job leaves it RUNNING (Refs: ISSUE-057)."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            cfg = AppConfig(
                app_env="test",
                log_to_file=False,
                data_dir=data_dir,
                database_url=f"sqlite:///{data_dir / 'app.db'}",
            )
            engine = create_db_engine(cfg.database_url)
            Base.metadata.create_all(engine)
            factory = make_session_factory(engine)

            @contextmanager
            def _lit_scope() -> Iterator[LiteratureManager]:
                with factory() as session:
                    yield LiteratureManager(
                        cfg,
                        LiteratureRepository(session),
                        CourseRepository(session),
                        AdapterLiteratureRuntime(cfg),
                    )

            started_event = threading.Event()
            release_event = threading.Event()
            done_event = threading.Event()

            def _blocking_process(_opts: object) -> list[object]:
                started_event.set()
                release_event.wait(timeout=5.0)
                return []

            runner1 = LiteratureJobRunner(
                _lit_scope, lock_path=cfg.literature_job_lock_path, lock_factory=RunLock
            )
            try:
                with patch.object(LiteratureManager, "process_items", side_effect=_blocking_process):
                    job = runner1.start("download", JobRunOptions(on_done=done_event.set))
                    self.assertTrue(started_event.wait(timeout=3.0))

                    # Second runner simulates MCP stdio / separate OS process booting mid-job.
                    runner2 = LiteratureJobRunner(
                        _lit_scope, lock_path=cfg.literature_job_lock_path, lock_factory=RunLock
                    )
                    self.assertIsNotNone(runner2)
                    with factory() as session:
                        mid_job = LiteratureRepository(session).latest_job()
                    self.assertIsNotNone(mid_job)
                    assert mid_job is not None
                    self.assertEqual((mid_job.id, mid_job.state), (job.id, JobState.RUNNING))

                    with self.assertRaises(AlreadyRunningError):
                        runner2.start("download")
                release_event.set()
                self.assertTrue(done_event.wait(timeout=3.0))
                if runner1._thread is not None:
                    runner1._thread.join(timeout=3.0)
            finally:
                release_event.set()
                if runner1._thread is not None:
                    runner1._thread.join(timeout=3.0)

            with factory() as session:
                finished = LiteratureRepository(session).latest_job()
            self.assertIsNotNone(finished)
            assert finished is not None
            self.assertEqual((finished.id, finished.state), (job.id, JobState.DONE))

    def test_job_left_running_without_lock_holder_is_closed(self) -> None:
        """A running DB row with no OS lock holder is marked FAILED when a runner starts (Refs: ISSUE-057)."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            cfg = AppConfig(
                app_env="test",
                log_to_file=False,
                data_dir=data_dir,
                database_url=f"sqlite:///{data_dir / 'app.db'}",
            )
            engine = create_db_engine(cfg.database_url)
            Base.metadata.create_all(engine)
            factory = make_session_factory(engine)
            with factory() as session:
                orphaned = LiteratureRepository(session).start_job("download", 10, "orphan")

            @contextmanager
            def _lit_scope() -> Iterator[LiteratureManager]:
                with factory() as session:
                    yield LiteratureManager(
                        cfg,
                        LiteratureRepository(session),
                        CourseRepository(session),
                        AdapterLiteratureRuntime(cfg),
                    )

            LiteratureJobRunner(_lit_scope, lock_path=cfg.literature_job_lock_path, lock_factory=RunLock)
            with factory() as session:
                closed = LiteratureRepository(session).latest_job()
            self.assertIsNotNone(closed)
            assert closed is not None
            self.assertEqual((closed.id, closed.state), (orphaned.id, JobState.FAILED))
            self.assertNotEqual(closed.finished_at, "")


if __name__ == "__main__":
    unittest.main()

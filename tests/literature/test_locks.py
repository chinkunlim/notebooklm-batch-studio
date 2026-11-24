"""Tests for the cross-process literature run lock (ported from literature-fetch)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from notebooklm_batch_studio.adapters.locks import RunLock
from notebooklm_batch_studio.domain.literature.tracker import AlreadyRunningError


class RunLockTest(unittest.TestCase):
    """Only one process holds the OS file lock at a time."""

    def test_second_lock_fails_until_released(self) -> None:
        """A second holder is refused while the first holds the lock, and succeeds afterwards."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.lock"
            with RunLock(path):
                with self.assertRaises(AlreadyRunningError):
                    RunLock(path).__enter__()
            with RunLock(path):
                pass


if __name__ == "__main__":
    unittest.main()

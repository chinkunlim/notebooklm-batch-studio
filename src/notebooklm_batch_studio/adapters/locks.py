"""Process-wide run lock: only one background literature job runs across OS processes.

Uses an OS advisory file lock (`fcntl.flock`) under `DATA_DIR/state/`, released automatically
when the owning process releases the lock or terminates (Refs: ISSUE-057).
"""

from __future__ import annotations

import fcntl
import logging
import os
from pathlib import Path
from types import TracebackType

from notebooklm_batch_studio.domain.literature.tracker import AlreadyRunningError

logger = logging.getLogger(__name__)


class RunLock:
    """Exclusive, non-blocking OS advisory file lock."""

    def __init__(self, path: Path) -> None:
        """Create the lock handle without taking the lock yet.

        Args:
            path: Lock file path under the application state directory.
        """
        self._path = path
        self._fd: int | None = None

    def __enter__(self) -> RunLock:
        """Acquire the exclusive lock without blocking.

        Returns:
            This `RunLock` instance.

        Raises:
            AlreadyRunningError: When another process or runner holds the lock.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise AlreadyRunningError("another job is running") from exc
        self._fd = fd
        logger.info("run lock taken path=%s", self._path)
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        """Release the OS file lock and close its file descriptor.

        Args:
            exc_type: Exception class, if any.
            exc: Exception instance, if any.
            tb: Traceback, if any.
        """
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None
        logger.info("run lock released path=%s", self._path)

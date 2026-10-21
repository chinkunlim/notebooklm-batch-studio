"""Course folder watcher: detects newly added lecture PDFs and triggers automatic processing.

Monitors `DATA_DIR/input/courses/` recursively, ensures incoming files have finished
copying, and invokes orchestrator callbacks to scan and enqueue new jobs.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

logger = logging.getLogger(__name__)


def _wait_for_file_settled(file_path: Path, max_wait: float = 10.0, check_interval: float = 0.5) -> bool:
    """Ensure a newly created file has finished being written by checking size stability.

    Args:
        file_path: Path to the incoming file.
        max_wait: Maximum seconds to wait.
        check_interval: Seconds between size probes.

    Returns:
        True if file size remained stable and non-zero, False if timeout or missing.
    """
    if not file_path.exists():
        return False

    deadline = time.time() + max_wait
    last_size = -1

    while time.time() < deadline:
        try:
            curr_size = file_path.stat().st_size
            if curr_size > 0 and curr_size == last_size:
                return True
            last_size = curr_size
        except OSError:
            pass
        time.sleep(check_interval)

    return file_path.exists() and file_path.stat().st_size > 0


class CoursePdfEventHandler(FileSystemEventHandler):
    """File system event handler targeting course lecture PDFs."""

    def __init__(
        self,
        watch_root: Path,
        on_pdf_detected: Callable[[Path, Path], None],
    ) -> None:
        """Initialize the handler.

        Args:
            watch_root: Base courses input directory (DATA_DIR/input/courses).
            on_pdf_detected: Callback receiving (course_dir, pdf_path).
        """
        super().__init__()
        self.watch_root = watch_root.resolve()
        self.on_pdf_detected = on_pdf_detected

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle new file creation events.

        Args:
            event: Filesystem event details.
        """
        if event.is_directory:
            return
        src_path_str = os.fsdecode(event.src_path)
        self._process_event_path(Path(src_path_str))

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move/rename events.

        Args:
            event: Filesystem event details.
        """
        if event.is_directory:
            return
        dest_path = getattr(event, "dest_path", None)
        if dest_path:
            dest_str = os.fsdecode(dest_path)
            self._process_event_path(Path(dest_str))

    def _process_event_path(self, target_path: Path) -> None:
        """Verify and forward detected PDF files.

        Args:
            target_path: File system path of the event.
        """
        if target_path.suffix.lower() != ".pdf":
            return

        resolved = target_path.resolve()
        try:
            rel = resolved.relative_to(self.watch_root)
        except ValueError:
            return

        # Path must be inside a course folder: <watch_root>/<COURSE_CODE>/filename.pdf
        if len(rel.parts) < 2:
            return

        course_dir = self.watch_root / rel.parts[0]
        logger.info("Detected new PDF: %s in course %s", resolved.name, course_dir.name)

        if _wait_for_file_settled(resolved):
            try:
                self.on_pdf_detected(course_dir, resolved)
            except Exception as err:
                logger.error("Error invoking on_pdf_detected callback: %s", err)
        else:
            logger.warning("File %s did not stabilize within timeout; skipping.", resolved.name)


class CourseWatcher:
    """Manages background directory monitoring for incoming course lectures."""

    def __init__(
        self,
        watch_root: Path,
        on_pdf_detected: Callable[[Path, Path], None],
    ) -> None:
        """Initialize the watcher service.

        Args:
            watch_root: Path to input courses directory.
            on_pdf_detected: Callback invoked when a new lecture PDF is ready.
        """
        self.watch_root = watch_root
        self.on_pdf_detected = on_pdf_detected
        self.observer: BaseObserver | None = None

    def start(self) -> None:
        """Start the background filesystem observer."""
        self.watch_root.mkdir(parents=True, exist_ok=True)
        handler = CoursePdfEventHandler(self.watch_root, self.on_pdf_detected)
        self.observer = Observer()
        self.observer.schedule(handler, str(self.watch_root), recursive=True)
        self.observer.start()
        logger.info("Started CourseWatcher monitoring on %s", self.watch_root)

    def stop(self) -> None:
        """Stop the background filesystem observer."""
        if self.observer and self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            logger.info("Stopped CourseWatcher.")

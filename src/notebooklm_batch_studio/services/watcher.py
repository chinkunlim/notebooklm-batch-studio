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

from notebooklm_batch_studio.domain.path_safety import is_within
from notebooklm_batch_studio.domain.study_layout import DEFAULT_LAYOUT, CategoryRole, StudyLayout

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

    # Restricts triggers to HANDOUTS PDFs inside registered study courses.

    def __init__(
        self,
        watch_root: Path,
        resolve_course: Callable[[Path], Path | None],
        on_pdf_detected: Callable[[Path, Path], None],
        layout: StudyLayout = DEFAULT_LAYOUT,
    ) -> None:
        """Initialize the handler.

        Args:
            watch_root: Base study library directory (`DATA_DIR/study`).
            resolve_course: Callback resolving a PDF path to its registered course directory, or None.
            on_pdf_detected: Callback receiving `(course_dir, pdf_path)`.
            layout: Study category layout identifying `CategoryRole.HANDOUTS`.
        """
        super().__init__()
        self.watch_root = watch_root.resolve()
        self.resolve_course = resolve_course
        self.on_pdf_detected = on_pdf_detected
        self.layout = layout

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

        Accepts PDFs inside a registered course's HANDOUTS category.

        Args:
            target_path: File system path of the event.
        """
        if target_path.name.startswith(".") or target_path.suffix.lower() != ".pdf":
            return
        resolved = target_path.resolve()
        if not is_within(resolved, self.watch_root):
            return
        raw_course_dir = self.resolve_course(resolved)
        if raw_course_dir is None:
            return
        course_dir = raw_course_dir.resolve()
        try:
            rel = resolved.relative_to(course_dir)
        except ValueError:
            return
        if len(rel.parts) < 2 or self.layout.role_of(rel.parts[0]) != CategoryRole.HANDOUTS:
            return
        logger.info("Detected new handout PDF: %s in course %s", resolved.name, course_dir.name)
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
        resolve_course: Callable[[Path], Path | None] | None = None,
        layout: StudyLayout = DEFAULT_LAYOUT,
    ) -> None:
        """Initialize the watcher service.

        Args:
            watch_root: Path to study root directory (`DATA_DIR/study`).
            on_pdf_detected: Callback invoked when a new handout PDF is ready.
            resolve_course: Optional resolver mapping PDF path -> registered course directory.
            layout: Study category layout configuration.
        """
        self.watch_root = watch_root
        self.on_pdf_detected = on_pdf_detected
        self.resolve_course = resolve_course
        self.layout = layout
        self.observer: BaseObserver | None = None

    def start(self) -> None:
        """Start the background filesystem observer."""
        self.watch_root.mkdir(parents=True, exist_ok=True)
        resolver = self.resolve_course or (
            lambda p: self.watch_root / p.relative_to(self.watch_root).parts[0]
        )
        handler = CoursePdfEventHandler(self.watch_root, resolver, self.on_pdf_detected, layout=self.layout)
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

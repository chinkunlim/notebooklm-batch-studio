"""Background schedule for Gemini chapter notes: approved chapters run in order, resume after quota."""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.domain.note_pipeline import STANDARD_NOTE_STEPS
from notebooklm_batch_studio.services.notes.note_paths import ChapterNoteRequest

logger = logging.getLogger(__name__)

DEFAULT_QUOTA_WAIT = timedelta(hours=1)
IDLE_SECONDS = 15.0
_ACTIVE = ("pending", "running", "quota_wait")
_FINISHED = ("done", "failed")


class NotePipelineProtocol(Protocol):
    """The part of NotePipelineService the scheduler uses."""

    def run_chapter(self, request: ChapterNoteRequest) -> dict[str, Any]:
        """Generate one chapter.

        Args:
            request: Chapter request.

        Returns:
            Result with `status` (`done`, `quota_wait`, `paused`) and optional `resume_after`.
        """
        ...

    def get_status(self, course_key: str) -> dict[str, Any]:
        """Return per-chapter state.

        Args:
            course_key: Course identifier.

        Returns:
            `{"chapters": {chapter_id: {...}}}`.
        """
        ...


def _iso(dt: datetime) -> str:
    """Format a datetime as ISO text.

    Args:
        dt: Aware datetime.

    Returns:
        ISO 8601 string.
    """
    return dt.isoformat()


def _lecture_item(course: Course, lecture: Any) -> dict[str, Any]:
    """Build one schedule item from a course lecture.

    Args:
        course: Registered course.
        lecture: Lecture entity.

    Returns:
        Schedule item dictionary.
    """
    chapter_id = f"ch{lecture.no:02d}"
    rel = lecture.relative_path or lecture.filename
    return {
        "id": f"{course.code}:{chapter_id}",
        "course_key": course.code,
        "course_name": course.name,
        "chapter_id": chapter_id,
        "lecture_no": lecture.no,
        "chapter_title": lecture.topic or Path(lecture.filename).stem,
        "pdf_path": str(Path(course.source_dir) / rel) if course.source_dir else "",
        "notebook_id": course.notebook_id or "",
        "source_ids": [lecture.source_id] if lecture.source_id else [],
        "study_dir": course.study_dir or "",
        "status": "pending",
        "resume_at": None,
        "completed_steps": [],
        "last_error": "",
    }


def _request_for(item: dict[str, Any]) -> ChapterNoteRequest:
    """Turn a schedule item into a pipeline request (only unfinished modules after a quota stop).

    Args:
        item: Schedule item.

    Returns:
        ChapterNoteRequest.
    """
    done = set(item.get("completed_steps") or [])
    remaining = [s.step_id for s in STANDARD_NOTE_STEPS if s.step_id not in done] if done else None
    return ChapterNoteRequest(
        course_key=item["course_key"],
        course_name=item["course_name"],
        chapter_id=item["chapter_id"],
        chapter_title=item["chapter_title"],
        pdf_path=Path(item["pdf_path"]) if item.get("pdf_path") else None,
        notebook_id=item.get("notebook_id", ""),
        source_ids=list(item.get("source_ids") or []),
        steps_override=remaining,
        study_dir=Path(item["study_dir"]) if item.get("study_dir") else None,
    )


class NoteScheduler:
    """Persisted, single-worker queue of approved chapter-note jobs."""

    def __init__(
        self,
        state_path: Path,
        pipeline_factory: Callable[[], NotePipelineProtocol],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Bind the state file, pipeline factory and clock.

        Args:
            state_path: JSON file holding the schedule (`DATA_DIR/state/note_schedule.json`).
            pipeline_factory: Builds the note pipeline used for each chapter.
            clock: Returns the current aware time (tests inject a fixed clock).
        """
        self.state_path = state_path
        self.pipeline_factory = pipeline_factory
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _load(self) -> dict[str, Any]:
        """Read the schedule file.

        Returns:
            `{"paused": bool, "items": [...]}`.
        """
        if not self.state_path.is_file():
            return {"paused": False, "items": []}
        data: dict[str, Any] = json.loads(self.state_path.read_text(encoding="utf-8"))
        return data

    def _save(self, data: dict[str, Any]) -> None:
        """Write the schedule file atomically.

        Args:
            data: Schedule document.
        """
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(f".{self.state_path.name}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def _update(self, fn: Callable[[dict[str, Any]], Any]) -> Any:
        """Load, mutate and save the schedule under the lock.

        Args:
            fn: Mutator receiving the document; its return value is passed through.

        Returns:
            Whatever `fn` returns.
        """
        with self._lock:
            data = self._load()
            result = fn(data)
            self._save(data)
            return result

    def enqueue_course(self, course: Course, lecture_nos: list[int]) -> dict[str, int]:
        """Approve chapters of one course for background generation.

        Args:
            course: Registered course.
            lecture_nos: Lecture numbers to schedule.

        Returns:
            `{"added": n, "skipped": m}` (skipped = already scheduled and not finished).
        """
        wanted = [lec for lec in course.lectures if lec.no in set(lecture_nos)]

        def add(data: dict[str, Any]) -> dict[str, int]:
            """Append chapters that are not already active.

            Args:
                data: Schedule document.

            Returns:
                Added / skipped counts.
            """
            active = {i["id"] for i in data["items"] if i["status"] in _ACTIVE}
            new = [_lecture_item(course, lec) for lec in wanted]
            fresh = [i for i in new if i["id"] not in active]
            data["items"].extend({**i, "added_at": _iso(self.clock())} for i in fresh)
            return {"added": len(fresh), "skipped": len(new) - len(fresh)}

        result: dict[str, int] = self._update(add)
        logger.info("Note schedule for %s: %s", course.code, result)
        return result

    def status(self) -> dict[str, Any]:
        """Return the schedule with the next quota resume time.

        Returns:
            `{"paused", "running", "next_resume_at", "items"}`.
        """
        with self._lock:
            data = self._load()
        waits = sorted(
            i["resume_at"] for i in data["items"] if i["status"] == "quota_wait" and i.get("resume_at")
        )
        running = bool(self._thread and self._thread.is_alive())
        return {**data, "running": running, "next_resume_at": waits[0] if waits else None}

    def pause(self) -> dict[str, Any]:
        """Stop starting new chapters (the current module finishes).

        Returns:
            Updated status.
        """
        self._update(lambda d: d.__setitem__("paused", True))
        return self.status()

    def resume(self) -> dict[str, Any]:
        """Allow chapters to start again.

        Returns:
            Updated status.
        """
        self._update(lambda d: d.__setitem__("paused", False))
        return self.status()

    def recover(self) -> int:
        """Put chapters left `running` by a stopped server back to `pending`.

        Returns:
            Number of recovered items.
        """

        def fix(data: dict[str, Any]) -> int:
            """Reset running items to pending.

            Args:
                data: Schedule document.

            Returns:
                Number of reset items.
            """
            stuck = [i for i in data["items"] if i["status"] == "running"]
            for item in stuck:
                item["status"] = "pending"
            return len(stuck)

        count: int = self._update(fix)
        if count:
            logger.info("Recovered %d interrupted note chapters", count)
        return count

    def clear_finished(self) -> int:
        """Remove done and failed items from the list.

        Returns:
            Number of removed items.
        """

        def clear(data: dict[str, Any]) -> int:
            """Drop finished items.

            Args:
                data: Schedule document.

            Returns:
                Number of removed items.
            """
            before = len(data["items"])
            data["items"] = [i for i in data["items"] if i["status"] not in _FINISHED]
            return before - len(data["items"])

        removed: int = self._update(clear)
        return removed

    def _claim_next(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Pick the next runnable item and mark it running (caller holds the lock).

        Args:
            data: Schedule document.

        Returns:
            Claimed item copy, or None when paused, waiting for quota, or empty.
        """
        if data.get("paused"):
            return None
        now = self.clock()
        waiting = [i for i in data["items"] if i["status"] == "quota_wait"]
        if any(i.get("resume_at") and datetime.fromisoformat(i["resume_at"]) > now for i in waiting):
            return None  # same Gemini account: nothing starts until quota is back
        candidates = waiting + [i for i in data["items"] if i["status"] == "pending"]
        if not candidates:
            return None
        item = candidates[0]
        item["status"] = "running"
        item["started_at"] = _iso(now)
        return dict(item)

    def run_once(self) -> str | None:
        """Run the next runnable chapter to completion or interruption.

        Returns:
            The item's new status, or None when nothing could start.
        """
        claimed = self._update(self._claim_next)
        if claimed is None:
            return None
        pipeline = self.pipeline_factory()
        try:
            result = pipeline.run_chapter(_request_for(claimed))
        except Exception as exc:  # one bad chapter must not stop the schedule
            logger.exception("Scheduled note %s failed", claimed["id"])
            result = {"status": "failed", "error": str(exc)}
        new_status = self._apply_result(claimed, result, pipeline)
        logger.info("Scheduled note %s -> %s", claimed["id"], new_status)
        return new_status

    def _apply_result(
        self, claimed: dict[str, Any], result: dict[str, Any], pipeline: NotePipelineProtocol
    ) -> str:
        """Store a chapter result; quota stops keep finished modules and the reset time.

        Args:
            claimed: Item that ran.
            result: `run_chapter` result.
            pipeline: Pipeline used (for completed-module lookup).

        Returns:
            New item status.
        """
        status = str(result.get("status") or "failed")
        completed = list(claimed.get("completed_steps") or [])
        resume: str | None = None
        if status == "quota_wait":
            chapter = (
                pipeline.get_status(claimed["course_key"]).get("chapters", {}).get(claimed["chapter_id"], {})
            )
            completed = sorted(set(completed) | set(chapter.get("completed_steps") or []))
            resume = result.get("resume_after") or _iso(self.clock() + DEFAULT_QUOTA_WAIT)
        status = status if status in ("done", "quota_wait", "failed") else "pending"

        def store(data: dict[str, Any]) -> None:
            """Write the chapter's new status into the document.

            Args:
                data: Schedule document.
            """
            item = next(i for i in data["items"] if i["id"] == claimed["id"])
            item.update(status=status, last_error=str(result.get("error") or ""), completed_steps=completed)
            item["resume_at"] = resume if status == "quota_wait" else None
            if status in _FINISHED:
                item["finished_at"] = _iso(self.clock())
            if result.get("status") == "paused":
                data["paused"] = True  # the per-course pause button also pauses the schedule

        self._update(store)
        return status

    def start(self) -> None:
        """Start the background worker thread (idempotent)."""
        if self._thread and self._thread.is_alive():
            return
        self.recover()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="note-scheduler", daemon=True)
        self._thread.start()
        logger.info("Note scheduler started")

    def stop(self) -> None:
        """Ask the worker thread to stop after the current chapter."""
        self._stop.set()

    def _loop(self) -> None:
        """Run chapters until stopped; sleep when idle, paused, or waiting for quota."""
        while not self._stop.is_set():
            try:
                ran = self.run_once()
            except Exception:  # keep the worker alive on unexpected errors
                logger.exception("Note scheduler loop error")
                ran = None
            if ran is None:
                self._stop.wait(IDLE_SECONDS)

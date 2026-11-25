"""Build the course-complete callback that WorkerPool calls when a course has no work left (SPEC-017)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from notebooklm_batch_studio.config.settings import AppConfig

logger = logging.getLogger(__name__)

CourseCompleteHook = Callable[[str, dict[str, int]], None]
NotificationSender = Callable[[str, str], object]
_ATTENTION = ("failed", "needs_review")


def completion_message(course_code: str, counts: dict[str, int]) -> str:
    """Compose the notification body for a finished course.

    Args:
        course_code: Course identifier.
        counts: Job counts by status value for that course.

    Returns:
        Human-readable message.
    """
    done = counts.get("done", 0)
    attention = sum(counts.get(key, 0) for key in _ATTENTION)
    text = f"課程 {course_code} 全部產出完成（{done} 項）"
    return f"{text}，{attention} 項需處理" if attention else text


def course_complete_hook(config: AppConfig, send: NotificationSender) -> CourseCompleteHook | None:
    """Return the notification callback, or None when `NOTIFY_ON_COMPLETE` is off.

    Args:
        config: Application configuration.
        send: Notification sender `(title, message)` injected by the entrypoint (adapter layer).

    Returns:
        Callable `(course_code, counts) -> None`, or None.
    """
    if not config.notify_on_complete:
        return None

    def notify(course_code: str, counts: dict[str, int]) -> None:
        """Send the course-complete notification.

        Args:
            course_code: Course identifier.
            counts: Job counts by status value.
        """
        send("Gemini Notebook 學習工作室", completion_message(course_code, counts))

    return notify

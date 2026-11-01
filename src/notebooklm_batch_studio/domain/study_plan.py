"""Study plan rules: the recommended order of steps per lecture and the spaced-review schedule.

Pure domain logic with no I/O. The order follows evidence-based learning: get the big picture
(audio), read for understanding (study guide / concept explanation), retrieve with quizzes from
easy to hard, then keep it with spaced flashcard review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# (step key, label, artifact types that make the step available, how the step is completed)
STUDY_STEPS: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("audio", "🎧 聽語音摘要", ("audio",), "mark"),
    ("guide", "📘 讀讀書指南", ("study_guide", "reports_study_guide", "reports_concept_explanation"), "mark"),
    ("quiz_1", "📝 測驗 1・基礎", ("quiz_1",), "quiz"),
    ("quiz_2", "📝 測驗 2・理解", ("quiz_2",), "quiz"),
    ("quiz_3", "📝 測驗 3・模擬考", ("quiz_3",), "quiz"),
    ("flashcards", "🗂️ 閃卡複習", ("flashcards",), "review"),
)

MARKABLE_STEPS = frozenset(key for key, _, _, how in STUDY_STEPS if how == "mark")

# Days until the next review after each successful recall (stage 0 -> 1 day, ... -> 30 days).
REVIEW_INTERVAL_DAYS: tuple[int, ...] = (1, 3, 7, 14, 30)
# A forgotten item comes back later the same session.
RELEARN_MINUTES = 10


@dataclass(frozen=True)
class ReviewItem:
    """A flashcard or mistake on the spaced-review schedule.

    Attributes:
        id: Unique id "<kind>:<course>:<key>".
        course_code: Course identifier.
        lecture_no: Lecture number, or None for course-wide items.
        kind: 'flashcard' or 'mistake'.
        item_key: Stable key of the item.
        front: Prompt side.
        back: Answer side.
        stage: Current stage (index into REVIEW_INTERVAL_DAYS).
        due_at: Next review time (UTC).
        last_reviewed_at: Last review time, if any.
    """

    id: str
    course_code: str
    lecture_no: int | None
    kind: str
    item_key: str
    front: str
    back: str
    stage: int
    due_at: datetime
    last_reviewed_at: datetime | None = None


def next_schedule(stage: int, remembered: bool, now: datetime) -> tuple[int, datetime]:
    """Compute the next stage and due time after one review (a simple Leitner schedule).

    Args:
        stage: Current stage (0 for a new item).
        remembered: Whether the student recalled it.
        now: Review time.

    Returns:
        New stage and next due time: remembered moves one interval further (1, 3, 7, 14, 30
        days); forgotten goes back to stage 0 and returns in 10 minutes.
    """
    if not remembered:
        return 0, now + timedelta(minutes=RELEARN_MINUTES)
    new_stage = min(stage + 1, len(REVIEW_INTERVAL_DAYS))
    return new_stage, now + timedelta(days=REVIEW_INTERVAL_DAYS[new_stage - 1])

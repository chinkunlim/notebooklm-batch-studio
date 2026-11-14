"""Study plan rules: the recommended order of steps per lecture and the spaced-review schedule.

Pure domain logic with no I/O. The order follows evidence-based learning: get the big picture
(audio), read for understanding (study guide / concept explanation), retrieve with quizzes from
easy to hard, then keep it with spaced flashcard review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

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


def _is_step_done(
    lec_no: int,
    key: str,
    how: str,
    activity: tuple[set[tuple[int | None, str]], set[tuple[int | None, str]], set[int | None]],
) -> bool:
    """Check whether one lecture study step is completed based on activity sets.

    Args:
        lec_no: Lecture sequence number.
        key: Step identifier key.
        how: Completion mode ('mark', 'quiz', or 'review').
        activity: Tuple of (marks, attempted_quizzes, reviewed_lectures).

    Returns:
        True if completed, False otherwise.
    """
    marks, attempted, reviewed = activity
    if how == "mark":
        return (lec_no, key) in marks
    if how == "quiz":
        return any(no == lec_no and variant.startswith(key) for no, variant in attempted)
    return lec_no in reviewed


def compute_course_study_state(
    lecture_nos: list[int],
    done_types: set[tuple[int | None, str]],
    activity: tuple[set[tuple[int | None, str]], set[tuple[int | None, str]], set[int | None]],
) -> str:
    """Classify a course's study state as 'not_started', 'in_progress', or 'finished'.

    Args:
        lecture_nos: Ordered lecture sequence numbers in the course.
        done_types: Completed (lecture_no, artifact_type) pairs.
        activity: Tuple of (marks, attempted_quizzes, reviewed_lectures).

    Returns:
        'finished' when every available study step is completed, 'in_progress' when any
        study activity exists, or 'not_started' otherwise.
    """
    marks, attempted, reviewed = activity
    total_avail = 0
    total_done = 0
    for lec_no in lecture_nos:
        for key, _, types, how in STUDY_STEPS:
            if not any((lec_no, t) in done_types for t in types):
                continue
            total_avail += 1
            if _is_step_done(lec_no, key, how, activity):
                total_done += 1
    if lecture_nos and total_avail > 0 and total_done == total_avail:
        return "finished"
    if total_done > 0 or bool(marks or attempted or reviewed):
        return "in_progress"
    return "not_started"


@dataclass(frozen=True)
class StepStatusContext:
    """Pre-fetched course completion lookup sets used to evaluate per-lecture step state.

    Attributes:
        done_types: Completed (lecture_no, artifact_type) pairs.
        marks: Manually marked (lecture_no, step) pairs.
        attempted: Attempted (lecture_no, quiz_variant) pairs.
        reviewed: Lecture numbers with at least one reviewed flashcard.
    """

    done_types: set[tuple[int | None, str]]
    marks: set[tuple[int | None, str]]
    attempted: set[tuple[int | None, str]]
    reviewed: set[int | None]


def build_lecture_steps(
    lecture_no: int, ctx: StepStatusContext
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Compute step availability and completion flags for one lecture.

    Args:
        lecture_no: Target lecture sequence number.
        ctx: Pre-fetched completion sets across queue, manual marks, quizzes, and reviews.

    Returns:
        Tuple of (step dicts list, first unfinished available step dict or None).
    """
    steps: list[dict[str, Any]] = []
    first_todo: dict[str, Any] | None = None
    activity = (ctx.marks, ctx.attempted, ctx.reviewed)
    for key, label, types, how in STUDY_STEPS:
        available = any((lecture_no, t) in ctx.done_types for t in types)
        done = _is_step_done(lecture_no, key, how, activity)
        steps.append({"step": key, "label": label, "available": available, "done": done})
        if available and not done and first_todo is None:
            first_todo = {"step": key, "label": label}
    return steps, first_todo

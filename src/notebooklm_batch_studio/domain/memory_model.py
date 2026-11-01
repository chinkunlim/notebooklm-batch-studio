"""Forgetting-curve estimate of how well each lecture is remembered, plus study streaks.

Ebbinghaus-style exponential decay: retention R = exp(-t / S), where t is days since the last
practice and S ("stability", in days) grows each time the material is recalled well. The numbers
are a study aid that tells the student what is fading, not a measurement.

- Quiz history: S starts at 1 day; a score >= 80% multiplies S by 2.5, >= 60% by 1.3, below 60%
  halves it (minimum half a day).
- Flashcards: the spaced-review stage already encodes the interval; S is chosen so that memory is
  about 70% on the day the card is due (S = interval * 2.8).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from notebooklm_batch_studio.domain.study_plan import REVIEW_INTERVAL_DAYS

#: Stability multiplier that puts retention at ~70% when a flashcard falls due.
CARD_STABILITY_FACTOR = 2.8
#: Retention bands shown to the student.
STRONG_AT = 70
FADING_AT = 40


def retention(days_since: float, stability_days: float) -> float:
    """Fraction still remembered after some days, by exponential decay.

    Args:
        days_since: Days since the last practice (negative counts as 0).
        stability_days: Memory stability in days (> 0).

    Returns:
        Retention between 0 and 1.
    """
    return math.exp(-max(days_since, 0.0) / max(stability_days, 0.01))


def quiz_stability(history: Sequence[tuple[datetime, float]]) -> float:
    """Memory stability built up by a lecture's quiz attempts.

    Args:
        history: (when, fraction correct) for each attempt, any order.

    Returns:
        Stability in days.
    """
    stability = 1.0
    for _, fraction in sorted(history, key=lambda h: h[0]):
        if fraction >= 0.8:
            stability *= 2.5
        elif fraction >= 0.6:
            stability *= 1.3
        else:
            stability = max(0.5, stability * 0.5)
    return stability


def card_stability(stage: int) -> float:
    """Memory stability of a flashcard at a spaced-review stage.

    Args:
        stage: Review stage (0 = just forgotten, 1.. = index + 1 into REVIEW_INTERVAL_DAYS).

    Returns:
        Stability in days.
    """
    if stage <= 0:
        return 0.5
    interval = REVIEW_INTERVAL_DAYS[min(stage, len(REVIEW_INTERVAL_DAYS)) - 1]
    return interval * CARD_STABILITY_FACTOR


def _level(percent: int) -> str:
    """Name the retention band.

    Args:
        percent: Retention in percent.

    Returns:
        'strong', 'fading' or 'weak'.
    """
    if percent >= STRONG_AT:
        return "strong"
    return "fading" if percent >= FADING_AT else "weak"


def lecture_memory(
    quizzes: Sequence[tuple[datetime, float]], cards: Sequence[tuple[datetime, int]], now: datetime
) -> dict[str, Any] | None:
    """Estimate how well one lecture is remembered now.

    Args:
        quizzes: (when, fraction correct) per quiz attempt.
        cards: (last reviewed, stage) per reviewed flashcard or mistake.
        now: Current time (timezone-aware).

    Returns:
        {"percent", "level", "days_since"} or None when the lecture was never practised.
    """
    signals: list[float] = []
    last: list[datetime] = []
    if quizzes:
        when = max(q[0] for q in quizzes)
        days = (now - when).total_seconds() / 86400
        signals.append(retention(days, quiz_stability(quizzes)))
        last.append(when)
    for reviewed, stage in cards:
        days = (now - reviewed).total_seconds() / 86400
        signals.append(retention(days, card_stability(stage)))
        last.append(reviewed)
    if not signals:
        return None
    percent = round(100 * sum(signals) / len(signals))
    days_since = (now - max(last)).total_seconds() / 86400
    return {"percent": percent, "level": _level(percent), "days_since": round(days_since, 1)}


def study_streak(days: Iterable[date], today: date) -> int:
    """Consecutive study days ending today (or yesterday, so the streak survives until tonight).

    Args:
        days: Days with any study activity.
        today: Today's date.

    Returns:
        Streak length in days.
    """
    active = set(days)
    start = today if today in active else today - timedelta(days=1)
    streak = 0
    while start - timedelta(days=streak) in active:
        streak += 1
    return streak


def activity_heatmap(times: Iterable[datetime], today: date, weeks: int = 4) -> list[dict[str, Any]]:
    """Activity count per day for the last few weeks, oldest first.

    Args:
        times: Activity moments (already in the student's local time zone).
        today: Today's date.
        weeks: How many weeks to show.

    Returns:
        [{"date": "YYYY-MM-DD", "count": n}] for weeks * 7 days.
    """
    counts: dict[date, int] = {}
    for t in times:
        counts[t.date()] = counts.get(t.date(), 0) + 1
    span = weeks * 7
    return [
        {"date": d.isoformat(), "count": counts.get(d, 0)}
        for d in (today - timedelta(days=span - 1 - i) for i in range(span))
    ]

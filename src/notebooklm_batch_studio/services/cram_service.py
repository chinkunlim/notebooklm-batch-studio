"""Cramming & last-minute exam preparation service built on memory, mistakes, and QA notes."""

from __future__ import annotations

from datetime import date
from typing import Any

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.services.learning_service import LearningService


def parse_lectures_csv(raw: str) -> list[int]:
    """Parse a comma-separated lecture list such as '1,3,5' into sorted ints.

    Args:
        raw: Comma-separated lecture numbers (empty string = all).

    Returns:
        Sorted list of unique positive lecture numbers.
    """
    out: set[int] = set()
    for part in (raw or "").split(","):
        token = part.strip()
        if token.isdigit() and int(token) > 0:
            out.add(int(token))
    return sorted(out)


def _days_left(exam_date: str | None) -> int | None:
    """Return days remaining until exam_date (YYYY-MM-DD), or None if unset/invalid.

    Args:
        exam_date: Optional ISO date string.

    Returns:
        Integer day count (can be <= 0 on/after exam day) or None.
    """
    if not exam_date:
        return None
    try:
        return (date.fromisoformat(exam_date[:10]) - date.today()).days
    except ValueError:
        return None


def _lecture_weight(percent: int | None, mistakes: int) -> int:
    """Compute urgency weight for time allocation (higher = needs more study time).

    Args:
        percent: Memory strength 0-100 or None if unpracticed.
        mistakes: Count of unresolved mistakes for this lecture.

    Returns:
        Positive integer urgency weight.
    """
    base = 70 if percent is None else max(10, 100 - percent)
    return base + mistakes * 15


class CramService:
    """Aggregates high-risk lectures, unresolved mistakes, high-priority notes, and pacing."""

    def __init__(
        self,
        learning: LearningService,
        study_service: Any = None,
        qa_notes: Any = None,
    ) -> None:
        """Initialize CramService with learning, study, and optional QA notes services.

        Args:
            learning: LearningService for course lookup and memory strength.
            study_service: StudyTrackerService for unresolved quiz mistakes.
            qa_notes: Optional QANotesService for saved exploratory notes.
        """
        self.learning = learning
        self.study_service = study_service
        self.qa_notes = qa_notes

    def _collect_mistakes(self, code: str, selected: set[int]) -> tuple[dict[int, int], list[dict[str, Any]]]:
        """Count unresolved mistakes per lecture and serialize those in selected lectures.

        Args:
            code: Course identifier.
            selected: Set of selected lecture numbers.

        Returns:
            Tuple of (per-lecture mistake counts, serialized mistake dicts).
        """
        counts: dict[int, int] = {}
        items: list[dict[str, Any]] = []
        if self.study_service is None:
            return counts, items
        for m in self.study_service.get_weaknesses(code, only_unresolved=True):
            lno = m.lecture_no
            if lno is not None:
                counts[lno] = counts.get(lno, 0) + 1
            if selected and lno not in selected:
                continue
            items.append(
                {
                    "id": m.id,
                    "lecture_no": lno,
                    "question_text": m.question_text,
                    "choices": m.choices,
                    "correct_index": m.correct_index,
                }
            )
        return counts, items

    def _collect_notes(self, code: str, selected: set[int]) -> list[dict[str, Any]]:
        """Collect saved QA notes for selected lectures ordered by importance descending.

        Args:
            code: Course identifier.
            selected: Set of selected lecture numbers.

        Returns:
            List of high-priority QA note dicts.
        """
        if self.qa_notes is None:
            return []
        notes = self.qa_notes.list_notes(course_code=code)
        picked = [
            n for n in notes if not selected or n.get("lecture_no") in selected or n.get("lecture_no") is None
        ]
        picked.sort(key=lambda n: int(n.get("importance") or 1), reverse=True)
        return picked[:30]

    def _ranked_lectures(
        self, course: Course, selected: set[int], counts: dict[int, int], hours: float
    ) -> list[dict[str, Any]]:
        """Rank selected lectures by urgency and allocate recommended cram minutes.

        Args:
            course: Course domain object.
            selected: Selected lecture numbers (empty = all).
            counts: Unresolved mistake counts keyed by lecture_no.
            hours: Available study budget in hours.

        Returns:
            Sorted list of lecture cram summary dicts.
        """
        mem_map = {x["no"]: x for x in self.learning.memory(course.code).get("lectures", [])}
        rows: list[dict[str, Any]] = []
        for lec in course.lectures:
            if selected and lec.no not in selected:
                continue
            mem = mem_map.get(lec.no, {})
            pct = mem.get("percent")
            m_cnt = counts.get(lec.no, 0)
            w = _lecture_weight(pct, m_cnt)
            rows.append(
                {
                    "no": lec.no,
                    "topic": lec.topic,
                    "source_id": lec.source_id,
                    "percent": pct,
                    "level": mem.get("level"),
                    "mistake_count": m_cnt,
                    "weight": w,
                }
            )
        rows.sort(key=lambda r: r["weight"], reverse=True)
        total_w = sum(r["weight"] for r in rows) or 1
        total_min = max(15, round(max(0.25, hours) * 60))
        for r in rows:
            r["recommended_minutes"] = max(5, round(total_min * r["weight"] / total_w))
        return rows

    def build_cram_pack(
        self, code: str, lectures: list[int] | None = None, hours: float = 2.0
    ) -> dict[str, Any]:
        """Build a last-minute cramming pack for a course and optional lecture subset.

        Args:
            code: Course identifier.
            lectures: Optional list of lecture numbers; empty/None includes all lectures.
            hours: Available study hours used to compute per-lecture minutes.

        Returns:
            Dictionary with ranked lectures, pacing, mistakes, and high-priority notes.

        Raises:
            CourseNotFoundError: If course does not exist.
        """
        course = self.learning.course_repo.get_course(code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {code}")
        selected = set(lectures or [])
        counts, mistakes = self._collect_mistakes(code, selected)
        ranked = self._ranked_lectures(course, selected, counts, hours)
        notes = self._collect_notes(code, selected)
        return {
            "course_code": code,
            "days_until_exam": _days_left(course.exam_date),
            "hours_budget": hours,
            "lectures": ranked,
            "mistakes": mistakes,
            "high_priority_notes": notes,
        }

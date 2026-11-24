"""Student-facing study plan: what to do next per lecture, exam countdown, spaced review, explanations.

Combines what has been generated (artifact jobs), what the student has done (progress marks, quiz
attempts, flashcard reviews) and the exam date into one "today" view, and runs the spaced-review
schedule for flashcards and mistakes. "Why is this the answer?" asks Gemini Notebook about one quiz
question, grounded in the course's own sources.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
from datetime import UTC, date, datetime
from typing import Any, Protocol

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import Course, CourseStatus, JobStatus
from notebooklm_batch_studio.domain.notebooklm_protocol import NotebookLMClientProtocol
from notebooklm_batch_studio.domain.repositories import (
    CourseRepositoryProtocol,
    QueueRepositoryProtocol,
    StudyRepositoryProtocol,
)
from notebooklm_batch_studio.domain.study_plan import (
    MARKABLE_STEPS,
    ReviewItem,
    StepStatusContext,
    build_lecture_steps,
    next_schedule,
)
from notebooklm_batch_studio.services.converters.report_converter import markdown_fragment
from notebooklm_batch_studio.services.learning_service import strip_citations

logger = logging.getLogger(__name__)

REVIEW_KINDS = ("flashcard", "mistake")


class ReviewStoreProtocol(Protocol):
    """Storage the study plan needs for progress marks and review items."""

    def mark_step(self, course_code: str, lecture_no: int | None, step: str, done: bool) -> None:
        """Mark a step done or not done.

        Args:
            course_code: Course code.
            lecture_no: Lecture number or None.
            step: Step key.
            done: Whether it is done.
        """
        ...

    def list_steps(self, course_code: str) -> set[tuple[int | None, str]]:
        """List done steps.

        Args:
            course_code: Course code.

        Returns:
            Set of (lecture number, step).
        """
        ...

    def get_item(self, item_id: str) -> ReviewItem | None:
        """Load a review item.

        Args:
            item_id: Item id.

        Returns:
            The item or None.
        """
        ...

    def save_item(self, item: ReviewItem) -> None:
        """Insert or update a review item.

        Args:
            item: Review item.
        """
        ...

    def due_items(self, course_code: str, now: datetime, lecture_no: int | None = None) -> list[ReviewItem]:
        """List due items.

        Args:
            course_code: Course code.
            now: Current time.
            lecture_no: Optional lecture filter.

        Returns:
            Due items.
        """
        ...

    def reviewed_lectures(self, course_code: str, kind: str) -> set[int | None]:
        """Lectures with at least one reviewed item of a kind.

        Args:
            course_code: Course code.
            kind: Item kind.

        Returns:
            Lecture numbers.
        """
        ...

    def count_due(self, course_code: str, now: datetime) -> dict[str, int]:
        """Count due items per kind.

        Args:
            course_code: Course code.
            now: Current time.

        Returns:
            Kind to count.
        """
        ...

    def save_explanation(
        self, course_code: str, lecture_no: int | None, question_key: str, **content: Any
    ) -> None:
        """Save an explanation.

        Args:
            course_code: Course code.
            lecture_no: Lecture number or None.
            question_key: Hash of the question.
            **content: Must supply `question` and `answer_md`.
        """
        ...

    def get_explanation(self, course_code: str, question_key: str) -> dict[str, object] | None:
        """Load a saved explanation.

        Args:
            course_code: Course code.
            question_key: Hash of the question.

        Returns:
            Saved explanation or None.
        """
        ...

    def list_explanations(self, course_code: str, lecture_no: int | None = None) -> list[dict[str, object]]:
        """List saved explanations.

        Args:
            course_code: Course code.
            lecture_no: Optional lecture filter.

        Returns:
            Saved explanations.
        """
        ...


def days_until(exam_date: str | None, today: date) -> int | None:
    """Days from today to the exam date.

    Args:
        exam_date: 'YYYY-MM-DD' or None.
        today: Today's date.

    Returns:
        Number of days (0 = today, negative = past), or None when no valid date is set.
    """
    if not exam_date:
        return None
    try:
        return (date.fromisoformat(exam_date) - today).days
    except ValueError:
        return None


@dataclasses.dataclass(frozen=True)
class StudyPlanDeps:
    """Repository and client dependencies required by `StudyPlanService`."""

    course_repo: CourseRepositoryProtocol
    queue_repo: QueueRepositoryProtocol
    study_repo: StudyRepositoryProtocol
    review_repo: ReviewStoreProtocol
    notebooklm_client: NotebookLMClientProtocol


class StudyPlanService:
    """Builds the student's plan and runs spaced review and explanations."""

    def __init__(self, deps: StudyPlanDeps) -> None:
        """Bind the service to its stores and the Gemini Notebook client.

        Args:
            deps: Bundled repositories and Gemini Notebook client dependencies.
        """
        self.course_repo = deps.course_repo
        self.queue_repo = deps.queue_repo
        self.study_repo = deps.study_repo
        self.review_repo = deps.review_repo
        self.notebooklm_client = deps.notebooklm_client

    def _course(self, code: str) -> Course:
        """Load a course or raise.

        Args:
            code: Course code.

        Returns:
            The course.

        Raises:
            CourseNotFoundError: When it does not exist.
        """
        course = self.course_repo.get_course(code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {code}")
        return course

    def _step_context(self, code: str) -> StepStatusContext:
        """Assemble completion lookup sets across queue, review, and study repositories.

        Args:
            code: Course code.

        Returns:
            Pre-fetched StepStatusContext for evaluating per-lecture steps.
        """
        done_types = {
            (j.lecture_no, j.artifact_type.value)
            for j in self.queue_repo.list_jobs(course_code=code)
            if j.status == JobStatus.DONE
        }
        return StepStatusContext(
            done_types=done_types,
            marks=self.review_repo.list_steps(code),
            attempted={(a.lecture_no, a.quiz_variant) for a in self.study_repo.list_attempts(code)},
            reviewed=self.review_repo.reviewed_lectures(code, "flashcard"),
        )

    def get_today(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Build study plans for all active (non-archived) courses.

        Args:
            now: Current time (tests pass a fixed time).

        Returns:
            List of per-course study plan dictionaries for active courses.
        """
        active = self.course_repo.list_courses(status=CourseStatus.ACTIVE)
        return [self.get_plan(c.code, now=now) for c in active]

    def get_plan(self, code: str, now: datetime | None = None) -> dict[str, Any]:
        """Build today's plan: per-lecture steps, the next step, progress, exam countdown, reviews due.

        Args:
            code: Course code.
            now: Current time (tests pass a fixed time).

        Returns:
            Dictionary with `exam_date`, `days_left`, `due` counts, `next` (the first unfinished
            step of the course) and `lectures` (steps with available / done flags and percent).
        """
        now = now or datetime.now(UTC)
        course = self._course(code)
        archived = course.status == CourseStatus.ARCHIVED
        ctx = self._step_context(code)
        lectures, next_step = [], None
        for lec in course.lectures:
            steps, first_todo = build_lecture_steps(lec.no, ctx)
            if first_todo is not None and next_step is None and not archived:
                next_step = {"lecture_no": lec.no, "topic": lec.topic, **first_todo}
            usable = [s for s in steps if s["available"]]
            pct = round(100 * sum(1 for s in usable if s["done"]) / len(usable)) if usable else 0
            lectures.append({"lecture_no": lec.no, "topic": lec.topic, "steps": steps, "percent": pct})
        mistakes = 0 if archived else len(self.study_repo.list_mistakes(code, only_unresolved=True))
        flashcards = 0 if archived else self.review_repo.count_due(code, now).get("flashcard", 0)
        return {
            "code": code,
            "name": course.name,
            "exam_date": course.exam_date,
            "days_left": days_until(course.exam_date, now.date()),
            "archived": archived,
            "due": {"flashcards": flashcards, "mistakes": mistakes},
            "next": next_step,
            "lectures": lectures,
        }

    def mark_step(self, code: str, lecture_no: int | None, step: str, done: bool = True) -> dict[str, Any]:
        """Mark a reading / listening step done (quizzes and flashcards are tracked automatically).

        Args:
            code: Course code.
            lecture_no: Lecture number.
            step: 'audio' or 'guide'.
            done: True to mark done, False to undo.

        Returns:
            The updated plan.

        Raises:
            ValueError: For a step that is not marked by hand.
        """
        if step not in MARKABLE_STEPS:
            raise ValueError(f"Step cannot be marked by hand: {step}")
        self._course(code)
        self.review_repo.mark_step(code, lecture_no, step, done)
        return self.get_plan(code)

    def record_review(self, code: str, kind: str, item_key: str, **details: Any) -> dict[str, Any]:
        """Record one review and schedule the next (1, 3, 7, 14, 30 days; forgotten = 10 minutes).

        Args:
            code: Course code.
            kind: 'flashcard' or 'mistake'.
            item_key: Stable item key (for a flashcard, use `card_key(front)`).
            **details: Review options (`remembered`, `lecture_no`, `front`, `back`, `now`).

        Returns:
            The item's new stage and due time.

        Raises:
            ValueError: For an unknown kind.
        """
        if kind not in REVIEW_KINDS:
            raise ValueError(f"kind must be one of {', '.join(REVIEW_KINDS)}")
        remembered = bool(details["remembered"])
        now: datetime = details.get("now") or datetime.now(UTC)
        item_id = f"{kind}:{code}:{item_key}"
        current = self.review_repo.get_item(item_id)
        stage, due_at = next_schedule(current.stage if current else 0, remembered, now)
        item = ReviewItem(
            id=item_id,
            course_code=code,
            lecture_no=details.get("lecture_no") if current is None else current.lecture_no,
            kind=kind,
            item_key=item_key,
            front=str(details.get("front", "")) or (current.front if current else ""),
            back=str(details.get("back", "")) or (current.back if current else ""),
            stage=stage,
            due_at=due_at,
            last_reviewed_at=now,
        )
        self.review_repo.save_item(item)
        return {"id": item_id, "stage": stage, "due_at": due_at.isoformat()}

    def due_reviews(
        self, code: str, lecture_no: int | None = None, now: datetime | None = None
    ) -> list[dict[str, Any]]:
        """List the review items due now.

        Args:
            code: Course code.
            lecture_no: Optional lecture filter.
            now: Current time.

        Returns:
            Due items with front, back, kind, key, stage and lecture.
        """
        course = self.course_repo.get_course(code)
        if course is None or course.status == CourseStatus.ARCHIVED:
            return []
        items = self.review_repo.due_items(code, now or datetime.now(UTC), lecture_no)
        return [
            {
                "kind": i.kind,
                "key": i.item_key,
                "lecture_no": i.lecture_no,
                "front": i.front,
                "back": i.back,
                "stage": i.stage,
            }
            for i in items
        ]

    @staticmethod
    def _build_explanation_prompt(question: str, choices: list[str], answer_index: int) -> str:
        """Validate choices and build the Traditional Chinese tutor explanation prompt.

        Args:
            question: Question stem text.
            choices: Options in display order.
            answer_index: Zero-based index of the correct choice.

        Returns:
            Formatted tutor prompt string.
        """
        if not 0 <= answer_index < len(choices):
            raise ValueError("answer_index is out of range")
        letters = "ABCDEFGH"
        options = "\n".join(f"{letters[i]}. {c}" for i, c in enumerate(choices))
        return (
            "請只根據來源內容，用繁體中文、像老師對學生一樣說明：\n"
            f"題目：{question}\n選項：\n{options}\n"
            f"為什麼正確答案是 {letters[answer_index]}？請先用一兩句白話說明關鍵概念，"
            "再逐一說明其他選項錯在哪裡，最後給一個幫助記憶的小提示。"
        )

    async def _ask_and_save_explanation(
        self, course: Course, lecture_no: int | None, question: str, **opts: Any
    ) -> dict[str, Any]:
        """Query Gemini Notebook for a question explanation and persist it locally.

        Args:
            course: Domain Course entity.
            lecture_no: Lecture number or None for course-wide scope.
            question: Question stem text.
            **opts: Required `choices` (list[str]), `answer_index` (int), and `key` (str).

        Returns:
            Explanation payload with `answer`, `html`, `saved_at`, and `from_cache=False`.
        """
        if not course.notebook_id:
            raise ValueError("This course has no Gemini Notebook notebook yet")
        key = str(opts["key"])
        prompt = self._build_explanation_prompt(question, list(opts["choices"]), int(opts["answer_index"]))
        sources = [
            lec.source_id
            for lec in course.lectures
            if lec.source_id and (lecture_no is None or lec.no == lecture_no)
        ]
        answer = strip_citations(
            await self.notebooklm_client.ask(course.notebook_id, prompt, sources or None)
        )
        self.review_repo.save_explanation(course.code, lecture_no, key, question=question, answer_md=answer)
        logger.info("Explained and saved a quiz question for %s L%s", course.code, lecture_no)
        saved = self.review_repo.get_explanation(course.code, key) or {}
        return {
            "answer": answer,
            "html": markdown_fragment(answer),
            "saved_at": saved.get("created_at"),
            "from_cache": False,
        }

    async def explain(
        self, code: str, lecture_no: int | None, question: str, **details: Any
    ) -> dict[str, Any]:
        """Explain why an answer is correct: the saved explanation, or ask Gemini Notebook and save it.

        Every Gemini Notebook answer is kept, so the same question never spends quota twice unless the
        student asks again on purpose (`force`).

        Args:
            code: Course code.
            lecture_no: Lecture number, or None for course-wide questions.
            question: Question text.
            **details: Must include `choices` and `answer_index`; optional `force` (bool).

        Returns:
            Dictionary with `answer` (Markdown), `html`, `saved_at` and `from_cache`.

        Raises:
            ValueError: When the course has no notebook yet or the answer index is invalid.
        """
        course = self._course(code)
        key = card_key(question)
        force = bool(details.get("force", False))
        cached = None if force else self.review_repo.get_explanation(code, key)
        if cached:
            answer_md = str(cached["answer_md"])
            return {
                "answer": answer_md,
                "html": markdown_fragment(answer_md),
                "saved_at": cached["created_at"],
                "from_cache": True,
            }
        return await self._ask_and_save_explanation(
            course,
            lecture_no,
            question,
            choices=details["choices"],
            answer_index=details["answer_index"],
            key=key,
        )

    def list_explanations(self, code: str, lecture_no: int | None = None) -> list[dict[str, Any]]:
        """Saved Gemini Notebook explanations for a course (or one lecture), newest first, with HTML.

        Args:
            code: Course code.
            lecture_no: Optional lecture filter.

        Returns:
            Explanations with key, question, answer, html and saved time.
        """
        items = self.review_repo.list_explanations(code, lecture_no)
        return [{**item, "html": markdown_fragment(str(item.get("answer_md", "")))} for item in items]


def card_key(front: str) -> str:
    """Stable key for a flashcard, from its front text.

    Args:
        front: Card front.

    Returns:
        A short hash.
    """
    return hashlib.sha256(front.strip().encode("utf-8")).hexdigest()[:16]

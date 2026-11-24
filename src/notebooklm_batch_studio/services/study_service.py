"""Study tracker service: manages student quiz history, mistakes, and Anki card exports."""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.models import QuizAttempt, QuizMistake
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol, StudyRepositoryProtocol
from notebooklm_batch_studio.domain.study_hierarchy import resolve_course_output_root
from notebooklm_batch_studio.services.converters.flashcard_converter import parse_notebooklm_flashcards

logger = logging.getLogger(__name__)

#: Confidence a student can give before answering (metacognition: "sure but wrong" matters most).
CONFIDENCE_LEVELS = ("sure", "unsure", "guess")


def _build_quiz_mistake(
    attempt_id: str, course_code: str, lecture_no: int | None, item: dict[str, Any]
) -> QuizMistake:
    """Convert a raw frontend mistake dictionary into a validated QuizMistake domain entity.

    Args:
        attempt_id: Parent QuizAttempt identifier.
        course_code: Course code.
        lecture_no: Lecture sequence number or None.
        item: Raw mistake dictionary supplied by caller.

    Returns:
        Constructed QuizMistake entity.
    """
    raw_conf = item.get("confidence")
    return QuizMistake(
        id=str(uuid.uuid4()),
        attempt_id=attempt_id,
        course_code=course_code,
        lecture_no=lecture_no,
        question_text=str(item.get("question_text", "")).strip(),
        choices=list(item.get("choices", [])),
        correct_index=int(item.get("correct_index", 0)),
        selected_index=int(item.get("selected_index", 0)),
        explanation=str(item.get("explanation", "")).strip(),
        is_resolved=False,
        confidence=raw_conf if raw_conf in CONFIDENCE_LEVELS else None,
    )


def _format_anki_row(m: QuizMistake, tag: str) -> list[str]:
    """Render one unresolved QuizMistake into `[front_html, back_html, tag]` for Anki CSV.

    Args:
        m: Domain QuizMistake entity.
        tag: Deck tag string for the CSV column.

    Returns:
        Three-element CSV row `[front_html, back_html, tag]`.
    """
    front_lines = [f"<strong>{m.question_text}</strong>", "<ol type='A'>"]
    front_lines.extend(f"<li>{choice}</li>" for choice in m.choices)
    front_lines.append("</ol>")
    correct_letter = chr(65 + m.correct_index) if 0 <= m.correct_index < 26 else "?"
    back_html = (
        f"<p style='color:#16a34a;'><strong>正確解答：選項 {correct_letter}</strong></p>"
        f"<div style='border-left: 3px solid #3b82f6; padding-left: 8px;'>{m.explanation}</div>"
    )
    return ["".join(front_lines), back_html, tag]


class StudyTrackerService:
    """Core domain service for tracking student attempts, weakness notebook, and Anki exports."""

    def __init__(
        self,
        study_repo: StudyRepositoryProtocol,
        config: AppConfig | None = None,
        course_repo: CourseRepositoryProtocol | None = None,
    ) -> None:
        """Initialize the study tracker service.

        Args:
            study_repo: Data repository implementing StudyRepositoryProtocol.
            config: Optional application configuration.
            course_repo: Optional course repository used to scope outputs to `course.study_dir`.
        """
        self.study_repo = study_repo
        self.config = config
        self.course_repo = course_repo

    def record_quiz_attempt(self, course_code: str, lecture_no: int | None, **payload: Any) -> QuizAttempt:
        """Record a completed quiz attempt and individual mistakes.

        Args:
            course_code: Course code.
            lecture_no: Lecture sequence number or None for course-wide.
            **payload: Attempt details (`quiz_variant`, `score`, `total_questions`,
                `mistakes_data`, `confidence_summary`).

        Returns:
            Saved domain QuizAttempt entity.
        """
        attempt_id = str(uuid.uuid4())
        mistakes_data = list(payload.get("mistakes_data", ()))
        mistakes = [_build_quiz_mistake(attempt_id, course_code, lecture_no, m) for m in mistakes_data]
        attempt = QuizAttempt(
            id=attempt_id,
            course_code=course_code,
            lecture_no=lecture_no,
            quiz_variant=str(payload["quiz_variant"]),
            score=int(payload["score"]),
            total_questions=int(payload["total_questions"]),
            mistakes=mistakes,
            confidence_summary=payload.get("confidence_summary"),
        )
        self.study_repo.record_attempt(attempt)
        logger.info(
            "Recorded quiz attempt %s for course %s with %d mistakes",
            attempt_id,
            course_code,
            len(mistakes),
        )
        return attempt

    def get_study_history(self, course_code: str, lecture_no: int | None = None) -> list[QuizAttempt]:
        """Retrieve student quiz submission history.

        Args:
            course_code: Course code.
            lecture_no: Optional lecture filter.

        Returns:
            List of QuizAttempt entities.
        """
        return self.study_repo.list_attempts(course_code, lecture_no=lecture_no)

    def get_weaknesses(
        self,
        course_code: str,
        lecture_no: int | None = None,
        only_unresolved: bool = True,
    ) -> list[QuizMistake]:
        """Retrieve recorded mistakes in the student weakness notebook.

        Args:
            course_code: Course code.
            lecture_no: Optional lecture filter.
            only_unresolved: Whether to exclude already mastered mistakes.

        Returns:
            List of QuizMistake entities.
        """
        return self.study_repo.list_mistakes(
            course_code, lecture_no=lecture_no, only_unresolved=only_unresolved
        )

    def resolve_weakness(self, mistake_id: str) -> bool:
        """Mark a student mistake as mastered/resolved.

        Args:
            mistake_id: UUID of the mistake.

        Returns:
            True if resolved, False if not found.
        """
        return self.study_repo.resolve_mistake(mistake_id)

    def export_weaknesses_to_anki_csv(self, course_code: str, lecture_no: int | None = None) -> str:
        """Export recorded mistakes into an Anki-compatible CSV deck.

        Args:
            course_code: Course identifier.
            lecture_no: Optional lecture filter.

        Returns:
            Formatted CSV string ready for Anki import.
        """
        mistakes = self.get_weaknesses(course_code, lecture_no=lecture_no, only_unresolved=True)
        output = io.StringIO()
        output.write("#separator:Comma\n")
        output.write("#html:true\n")
        output.write("#tags column:3\n")

        writer = csv.writer(output, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        tag = f"{course_code} Weakness"
        if lecture_no is not None:
            tag += f" L{lecture_no:02d}"

        for m in mistakes:
            writer.writerow(_format_anki_row(m, tag))

        logger.info("Exported %d weakness questions to Anki CSV for %s", len(mistakes), course_code)
        return output.getvalue()

    def get_lecture_flashcards(self, course_code: str, lecture_no: int) -> list[dict[str, Any]]:
        """Load and parse flashcards for a lecture for in-browser 3D review.

        Args:
            course_code: Course code.
            lecture_no: Lecture sequence number.

        Returns:
            List of flashcard dictionaries with front, back, and source.
        """
        if not self.config:
            return []

        # Flashcards live in the lecture folder "<NN>_<topic>/flashcards[_vN].json"; the lecture
        # number is in the folder name, not the file name. Newest version first. Refs: ISSUE-020
        # Scoped strictly to this course's output root (no cross-course glob). Refs: ISSUE-064
        course = self.course_repo.get_course(course_code) if self.course_repo else None
        study_dir = course.study_dir if course else ""
        course_dir = resolve_course_output_root(self.config.courses_output_dir, course_code, study_dir)
        candidates = list(course_dir.glob(f"{lecture_no:02d}_*/flashcards*.json"))
        matches = sorted(
            candidates,
            key=lambda f: int(f.stem.rpartition("_v")[2]) if "_v" in f.stem else 1,
            reverse=True,
        )

        if not matches:
            return []

        try:
            content = matches[0].read_text(encoding="utf-8")
            raw_data = json.loads(content)
            cards = parse_notebooklm_flashcards(raw_data)
            return [{"front": c.front, "back": c.back, "source": c.source} for c in cards]
        except Exception as exc:
            logger.warning("Failed to load flashcards for %s L%d: %s", course_code, lecture_no, exc)
            return []

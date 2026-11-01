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
from notebooklm_batch_studio.domain.repositories import StudyRepositoryProtocol
from notebooklm_batch_studio.services.converters.flashcard_converter import parse_notebooklm_flashcards

logger = logging.getLogger(__name__)


class StudyTrackerService:
    """Core domain service for tracking student attempts, weakness notebook, and Anki exports."""

    def __init__(
        self,
        study_repo: StudyRepositoryProtocol,
        config: AppConfig | None = None,
    ) -> None:
        """Initialize the study tracker service.

        Args:
            study_repo: Data repository implementing StudyRepositoryProtocol.
            config: Optional application configuration.
        """
        self.study_repo = study_repo
        self.config = config

    def record_quiz_attempt(
        self,
        course_code: str,
        lecture_no: int | None,
        quiz_variant: str,
        score: int,
        total_questions: int,
        mistakes_data: list[dict[str, Any]],
    ) -> QuizAttempt:
        """Record a completed quiz attempt and individual mistakes.

        Args:
            course_code: Course code.
            lecture_no: Lecture sequence number or None for course-wide.
            quiz_variant: Variant of quiz (e.g. academic, concept).
            score: Student score.
            total_questions: Total number of questions.
            mistakes_data: List of raw mistake dictionaries from frontend.

        Returns:
            Saved domain QuizAttempt entity.
        """
        attempt_id = str(uuid.uuid4())
        mistakes: list[QuizMistake] = []
        for m in mistakes_data:
            mistakes.append(
                QuizMistake(
                    id=str(uuid.uuid4()),
                    attempt_id=attempt_id,
                    course_code=course_code,
                    lecture_no=lecture_no,
                    question_text=str(m.get("question_text", "")).strip(),
                    choices=list(m.get("choices", [])),
                    correct_index=int(m.get("correct_index", 0)),
                    selected_index=int(m.get("selected_index", 0)),
                    explanation=str(m.get("explanation", "")).strip(),
                    is_resolved=False,
                )
            )

        attempt = QuizAttempt(
            id=attempt_id,
            course_code=course_code,
            lecture_no=lecture_no,
            quiz_variant=quiz_variant,
            score=score,
            total_questions=total_questions,
            mistakes=mistakes,
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
            # Build Front: question + numbered choices
            front_lines = [f"<strong>{m.question_text}</strong>", "<ol type='A'>"]
            for choice in m.choices:
                front_lines.append(f"<li>{choice}</li>")
            front_lines.append("</ol>")
            front_html = "".join(front_lines)

            # Build Back: correct answer + explanation
            correct_letter = chr(65 + m.correct_index) if 0 <= m.correct_index < 26 else "?"
            back_lines = [
                f"<p style='color:#16a34a;'><strong>正確解答：選項 {correct_letter}</strong></p>",
                f"<div style='border-left: 3px solid #3b82f6; padding-left: 8px;'>{m.explanation}</div>",
            ]
            back_html = "".join(back_lines)

            writer.writerow([front_html, back_html, tag])

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

        course_dir = self.config.courses_output_dir / course_code
        pattern = f"*L{lecture_no:02d}*Flashcards*.json"
        matches = list(course_dir.glob(f"**/{pattern}"))
        if not matches:
            # Fallback to general pattern
            pattern = f"*{lecture_no}*flashcard*.json"
            matches = list(course_dir.glob(f"**/{pattern}"))

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

"""Learning aids built on the course: lecture reader with key points, memory strength, streaks and tutor.

- Reader: serves the registered lecture PDF read-only (never moved or changed) and asks Gemini Notebook
  once per lecture for key points with verbatim quotes and page numbers, which the web page highlights.
- Memory: forgetting-curve estimate per lecture, study streak and a 4-week activity heatmap.
- Tutor: a Socratic tutor that guides with questions instead of giving answers; the conversation is
  saved locally and continued on Gemini Notebook. The notebook's own chat settings are never changed.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.memory_model import activity_heatmap, lecture_memory, study_streak
from notebooklm_batch_studio.domain.models import Course, Lecture
from notebooklm_batch_studio.domain.notebooklm_protocol import NotebookLMClientProtocol
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol
from notebooklm_batch_studio.services.converters.report_converter import markdown_fragment

logger = logging.getLogger(__name__)

#: How many key points to ask for per lecture.
KEY_POINT_COUNT = 12
#: Citation markers such as [1] or [2, 3] that Gemini Notebook puts in its answers.
_CITATION = re.compile(r"\s*\[\d+(?:\s*[,\-–]\s*\d+)*\]")
_FENCED_JSON = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.S)

KEY_POINTS_PROMPT = (
    "請只根據這份講義，挑出最重要的 {count} 個重點，依講義順序排列。"
    "每個重點都要附上講義中「逐字」出現的一句原文（保留原本的語言，10 到 80 個字元，"
    "不要改寫、不要加省略號、不要加引用編號），以及它所在的頁碼。"
    "只輸出 JSON 陣列，不要任何其他文字，格式："
    '[{{"quote": "講義原文", "page": 3, "importance": 3, "note": "用繁體中文一句話說明為什麼重要"}}]。'
    "importance：3 = 考試必考的核心、2 = 重要概念、1 = 補充細節。"
)

TUTOR_PROMPT = (
    "你是一位耐心的家教，只根據來源內容，用繁體中文，以蘇格拉底式提問引導我學習。"
    "規則：不要直接給完整答案；先問我一個引導問題，或給一個小提示，等我回答；"
    "我答對時具體說明對在哪裡並往下一步推進；我答錯時指出誤解，再給更小的提示；"
    "每次回覆不超過 150 字，最後一定以一個問題結尾。\n\n我的訊息：{message}"
)


class LearningStoreProtocol(Protocol):
    """Storage the learning service needs (implemented by LearningRepository)."""

    def save_key_points(self, course_code: str, lecture_no: int, points: list[dict[str, Any]]) -> None:
        """Save a lecture's key points.

        Args:
            course_code: Course code.
            lecture_no: Lecture number.
            points: Key points.
        """
        ...

    def get_key_points(self, course_code: str, lecture_no: int) -> dict[str, Any] | None:
        """Load a lecture's saved key points.

        Args:
            course_code: Course code.
            lecture_no: Lecture number.

        Returns:
            Saved points and time, or None.
        """
        ...

    def add_tutor_message(
        self, course_code: str, lecture_no: int | None, role: str, text: str, conversation_id: str | None
    ) -> None:
        """Append a tutor message.

        Args:
            course_code: Course code.
            lecture_no: Lecture number or None.
            role: 'student' or 'tutor'.
            text: Message text.
            conversation_id: Conversation id or None.
        """
        ...

    def tutor_messages(self, course_code: str, lecture_no: int | None) -> list[dict[str, Any]]:
        """List a tutor conversation.

        Args:
            course_code: Course code.
            lecture_no: Lecture number or None.

        Returns:
            Messages, oldest first.
        """
        ...

    def clear_tutor(self, course_code: str, lecture_no: int | None) -> None:
        """Delete a local tutor conversation.

        Args:
            course_code: Course code.
            lecture_no: Lecture number or None.
        """
        ...

    def activity_times(self, course_code: str) -> list[datetime]:
        """Study activity moments.

        Args:
            course_code: Course code.

        Returns:
            Datetimes.
        """
        ...

    def memory_signals(self, course_code: str) -> dict[int | None, dict[str, list[Any]]]:
        """Per-lecture quiz and review history.

        Args:
            course_code: Course code.

        Returns:
            Lecture number to signals.
        """
        ...


def parse_key_points(text: str) -> list[dict[str, Any]]:
    """Read the key-point JSON out of a Gemini Notebook answer and clean it.

    Accepts a fenced ```json block or a bare array, strips citation markers, keeps valid items only,
    clamps importance to 1-3 and drops duplicates.

    Args:
        text: Answer text.

    Returns:
        Key points: {quote, page (int or None), importance, note}.

    Raises:
        ValueError: When no JSON array can be read.
    """
    fenced = _FENCED_JSON.search(text)
    raw = fenced.group(1) if fenced else text[text.find("[") : text.rfind("]") + 1]
    try:
        items = json.loads(_CITATION.sub("", raw))
    except (json.JSONDecodeError, ValueError) as err:
        raise ValueError(f"Key points are not valid JSON: {err}") from err
    if not isinstance(items, list):
        raise ValueError("Key points must be a JSON array")
    points: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        quote = " ".join(str(item.get("quote", "")).split()).strip(" \"'「」…")
        if len(quote) < 4 or quote in seen:
            continue
        seen.add(quote)
        page = item.get("page")
        importance = item.get("importance", 2)
        points.append(
            {
                "quote": quote,
                "page": page if isinstance(page, int) and page > 0 else None,
                "importance": min(3, max(1, importance)) if isinstance(importance, int) else 2,
                "note": str(item.get("note", "")).strip(),
            }
        )
    return points


class LearningService:
    """Reader, key points, memory strength, streaks and tutor for one course."""

    def __init__(
        self,
        course_repo: CourseRepositoryProtocol,
        learning_repo: LearningStoreProtocol,
        notebooklm_client: NotebookLMClientProtocol,
    ) -> None:
        """Bind to the stores and the Gemini Notebook client.

        Args:
            course_repo: Courses and lectures.
            learning_repo: Key points, tutor messages and activity.
            notebooklm_client: Gemini Notebook client.
        """
        self.course_repo = course_repo
        self.learning_repo = learning_repo
        self.notebooklm_client = notebooklm_client

    def _lecture(self, code: str, lecture_no: int) -> tuple[Course, Lecture]:
        """Load a course and one of its lectures.

        Args:
            code: Course code.
            lecture_no: Lecture number.

        Returns:
            (course, lecture).

        Raises:
            CourseNotFoundError: When the course or lecture does not exist.
        """
        course = self.course_repo.get_course(code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {code}")
        lecture = next((lec for lec in course.lectures if lec.no == lecture_no), None)
        if lecture is None:
            raise CourseNotFoundError(f"Lecture {lecture_no} not found in {code}")
        return course, lecture

    def source_pdf(self, code: str, lecture_no: int) -> Path:
        """Path of a lecture's PDF in the course folder (read-only; refuses anything outside it).

        Args:
            code: Course code.
            lecture_no: Lecture number.

        Returns:
            The PDF path.

        Raises:
            CourseNotFoundError: Unknown course or lecture.
            PermissionError: When the file name points outside the course folder.
            FileNotFoundError: When the PDF is no longer there.
        """
        course, lecture = self._lecture(code, lecture_no)
        folder = Path(course.source_dir).resolve()
        path = (folder / lecture.filename).resolve()
        if not path.is_relative_to(folder):
            raise PermissionError(f"Lecture file is outside the course folder: {lecture.filename}")
        if not path.is_file():
            raise FileNotFoundError(f"Lecture PDF not found: {path.name}")
        return path

    def key_points(self, code: str, lecture_no: int) -> dict[str, Any]:
        """Saved key points of a lecture (empty when not generated yet).

        Args:
            code: Course code.
            lecture_no: Lecture number.

        Returns:
            {"points": [...], "created_at": iso or None}.
        """
        self._lecture(code, lecture_no)
        return self.learning_repo.get_key_points(code, lecture_no) or {"points": [], "created_at": None}

    async def generate_key_points(self, code: str, lecture_no: int, force: bool = False) -> dict[str, Any]:
        """Ask Gemini Notebook for a lecture's key points once, then reuse the saved copy.

        Args:
            code: Course code.
            lecture_no: Lecture number.
            force: Ask again even when key points are saved.

        Returns:
            {"points", "created_at", "from_cache"}.

        Raises:
            ValueError: When the lecture is not uploaded yet or the answer cannot be read.
        """
        course, lecture = self._lecture(code, lecture_no)
        saved = None if force else self.learning_repo.get_key_points(code, lecture_no)
        if saved:
            return {**saved, "from_cache": True}
        if not course.notebook_id or not lecture.source_id:
            raise ValueError("This lecture is not uploaded to Gemini Notebook yet")
        logger.info("Asking Gemini Notebook for key points of %s L%d", code, lecture_no)
        answer = await self.notebooklm_client.ask(
            course.notebook_id, KEY_POINTS_PROMPT.format(count=KEY_POINT_COUNT), [lecture.source_id]
        )
        points = parse_key_points(answer)
        self.learning_repo.save_key_points(code, lecture_no, points)
        logger.info("Saved %d key points for %s L%d", len(points), code, lecture_no)
        return {**(self.learning_repo.get_key_points(code, lecture_no) or {}), "from_cache": False}

    def memory(self, code: str, now: datetime | None = None) -> dict[str, Any]:
        """Memory strength per lecture, study streak and activity heatmap.

        Args:
            code: Course code.
            now: Current time (defaults to now, UTC).

        Returns:
            {"lectures": [{no, topic, percent, level, days_since}], "streak", "heatmap", "studied_today"}.

        Raises:
            CourseNotFoundError: Unknown course.
        """
        course = self.course_repo.get_course(code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {code}")
        now = now or datetime.now(UTC)
        signals = self.learning_repo.memory_signals(code)
        lectures = []
        for lec in course.lectures:
            sig = signals.get(lec.no, {"quizzes": [], "cards": []})
            estimate = lecture_memory(sig["quizzes"], sig["cards"], now)
            lectures.append({"no": lec.no, "topic": lec.topic, **(estimate or {"percent": None})})
        local_now = now.astimezone()
        local_times = [t.astimezone(local_now.tzinfo) for t in self.learning_repo.activity_times(code)]
        today = local_now.date()
        days = {t.date() for t in local_times}
        return {
            "lectures": lectures,
            "streak": study_streak(days, today),
            "studied_today": today in days,
            "heatmap": activity_heatmap(local_times, today),
        }

    def tutor_history(self, code: str, lecture_no: int | None) -> list[dict[str, Any]]:
        """The saved tutor conversation, with tutor replies rendered to HTML.

        Args:
            code: Course code.
            lecture_no: Lecture number, or None for the whole course.

        Returns:
            Messages with role, text, html and created_at.
        """
        return [
            {**m, "html": markdown_fragment(m["text"]) if m["role"] == "tutor" else None}
            for m in self.learning_repo.tutor_messages(code, lecture_no)
        ]

    async def ask_tutor(self, code: str, lecture_no: int | None, message: str) -> dict[str, Any]:
        """Send the student's message to the Socratic tutor and save both sides.

        Args:
            code: Course code.
            lecture_no: Lecture number, or None for the whole course.
            message: The student's message.

        Returns:
            The tutor's reply: {"text", "html"}.

        Raises:
            CourseNotFoundError: Unknown course.
            ValueError: Empty message, or the course is not uploaded yet.
        """
        course = self.course_repo.get_course(code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {code}")
        if not message.strip():
            raise ValueError("Message is empty")
        if not course.notebook_id:
            raise ValueError("This course has no Gemini Notebook notebook yet")
        sources = [
            lec.source_id
            for lec in course.lectures
            if lec.source_id and (lecture_no is None or lec.no == lecture_no)
        ]
        history = self.learning_repo.tutor_messages(code, lecture_no)
        conversation = next((m["conversation_id"] for m in reversed(history) if m["conversation_id"]), None)
        reply, new_conversation = await self.notebooklm_client.ask_in_conversation(
            course.notebook_id, TUTOR_PROMPT.format(message=message.strip()), sources or None, conversation
        )
        self.learning_repo.add_tutor_message(code, lecture_no, "student", message.strip(), new_conversation)
        self.learning_repo.add_tutor_message(code, lecture_no, "tutor", reply, new_conversation)
        logger.info("Tutor replied for %s L%s (conversation %s)", code, lecture_no, new_conversation)
        return {"text": reply, "html": markdown_fragment(reply)}

    def clear_tutor(self, code: str, lecture_no: int | None) -> None:
        """Start the tutor conversation over (deletes the local copy only).

        Args:
            code: Course code.
            lecture_no: Lecture number, or None for the whole course.
        """
        self.learning_repo.clear_tutor(code, lecture_no)
        logger.info("Tutor conversation cleared for %s L%s", code, lecture_no)

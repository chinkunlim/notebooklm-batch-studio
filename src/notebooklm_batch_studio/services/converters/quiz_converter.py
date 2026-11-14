"""Quiz converter: transforms Gemini Notebook raw quiz outputs into Markdown, PDF, and JSON.

Supports merging multiple 10-question extracts, deduplicating question stems,
generating student exam papers (題目卷.md, no answers) and teacher/study answer keys
(答案卷.md, full rationale per option and hints), plus printable PDFs via ReportLab.
"""

from __future__ import annotations

import hashlib
import logging
import random
import re
from dataclasses import replace
from typing import Any

from notebooklm_batch_studio.domain.models import Choice, Question, Quiz
from notebooklm_batch_studio.services.converters.quiz_formatter import (
    CHOICE_LABELS as CHOICE_LABELS,
)
from notebooklm_batch_studio.services.converters.quiz_formatter import (
    to_answer_markdown as to_answer_markdown,
)
from notebooklm_batch_studio.services.converters.quiz_formatter import (
    to_exam_markdown as to_exam_markdown,
)
from notebooklm_batch_studio.services.converters.quiz_formatter import (
    to_interactive_html as to_interactive_html,
)
from notebooklm_batch_studio.services.converters.quiz_formatter import (
    to_json as to_json,
)
from notebooklm_batch_studio.services.converters.quiz_formatter import (
    to_pdf as to_pdf,
)

logger = logging.getLogger(__name__)


_CHAPTER_TAG = re.compile(r"^\s*[【\[]\s*((?:Ch|L)\s*\d+|第\s*\d+\s*講)\s*[】\]]\s*", re.I)

# Options that point at other options ("以上皆是", "A 與 B") only make sense in their original order.
_POSITIONAL_OPTION = re.compile(
    r"以上|上述|皆是|皆非|都對|都錯|all of the above|none of the above|\b[A-D]\s*(和|與|及|、|and)", re.I
)


def _shuffle_choices(stem: str, choices: list[Choice]) -> list[Choice]:
    """Put the options in a stable pseudo-random order so the answer is not always A.

    Gemini Notebook tends to list the correct option first (about 70% "A" in a real course, ISSUE-021).
    The order is seeded by the question text, so the same question always shows the same order.

    Args:
        stem: Question text (seed).
        choices: Options in Gemini Notebook's order.

    Returns:
        Shuffled options, or the original order when an option refers to other options.
    """
    if len(choices) < 2 or any(_POSITIONAL_OPTION.search(c.text) for c in choices):
        return choices
    seed = int(hashlib.sha256(stem.encode("utf-8")).hexdigest()[:12], 16)
    shuffled = list(choices)
    random.Random(seed).shuffle(shuffled)
    return shuffled


def _parse_choices(raw_options: list[Any], stem: str) -> tuple[list[Choice], int]:
    """Convert raw Gemini Notebook answerOptions dictionaries into shuffled Choice objects.

    Args:
        raw_options: List of raw option dictionaries.
        stem: Question stem text used as deterministic shuffle seed.

    Returns:
        Tuple of (shuffled Choices list, 0-based correct answer index).
    """
    choices: list[Choice] = []
    for opt in raw_options:
        if not isinstance(opt, dict):
            continue
        choices.append(
            Choice(
                text=str(opt.get("text", "")).strip(),
                is_correct=bool(opt.get("isCorrect", False)),
                rationale=str(opt.get("rationale", "")).strip(),
            )
        )
    shuffled = _shuffle_choices(stem, choices)
    answer_index = next((i for i, c in enumerate(shuffled) if c.is_correct), 0)
    return shuffled, answer_index


def _parse_question_dict(
    q_dict: dict[str, Any],
    id_prefix: str,
    idx: int,
    source_pdf: str,
) -> Question | None:
    """Parse a single raw question dictionary into a Question entity.

    Args:
        q_dict: Raw question dictionary.
        id_prefix: Question ID prefix (e.g. 'BIO101-03-Q1').
        idx: 1-based question index.
        source_pdf: Original PDF filename.

    Returns:
        Populated Question entity, or None if invalid.
    """
    stem = str(q_dict.get("question", "")).strip()
    # Course-wide exams ask Gemini Notebook to start each stem with its chapter, e.g. "【Ch03】"; keep it
    # as the question's source so results can be scored per chapter.
    tag = _CHAPTER_TAG.match(stem)
    if tag:
        stem = stem[tag.end() :].strip()
        source_pdf = re.sub(r"\s+", "", tag.group(1))
    if not stem:
        return None
    choices, answer_index = _parse_choices(q_dict.get("answerOptions", []), stem)
    explanation = choices[answer_index].rationale if choices and answer_index < len(choices) else ""
    return Question(
        id=f"{id_prefix}-{idx:03d}",
        question=stem,
        choices=choices,
        answer_index=answer_index,
        explanation=explanation,
        hint=str(q_dict.get("hint", "")).strip(),
        source=source_pdf,
    )


def _extract_title_and_raw_questions(
    raw_data: dict[str, Any] | list[Any], lecture_no: int, variant: str, custom_title: str
) -> tuple[str, list[Any]]:
    """Extract quiz title and candidate question list from dict or list raw payload.

    Args:
        raw_data: Raw Gemini Notebook quiz JSON object or list.
        lecture_no: Sequence number of the lecture.
        variant: Quiz difficulty or variant label.
        custom_title: Caller-provided title override.

    Returns:
        Tuple of (resolved quiz title, raw question items list).
    """
    fallback = custom_title or f"[{lecture_no:02d}] Quiz {variant}"
    if isinstance(raw_data, dict):
        return (custom_title or str(raw_data.get("title", "")) or fallback), list(
            raw_data.get("questions", [])
        )
    if isinstance(raw_data, list):
        return fallback, raw_data
    return fallback, []


def parse_notebooklm_quiz(
    raw_data: dict[str, Any] | list[Any],
    course_code: str,
    lecture_no: int,
    **meta: Any,
) -> Quiz:
    """Parse raw Gemini Notebook quiz JSON into a domain Quiz entity.

    Args:
        raw_data: Raw JSON dictionary or question list extracted from Gemini Notebook.
        course_code: Course identifier (e.g. BIO101).
        lecture_no: Sequence number of the lecture.
        **meta: Optional `variant` (default '1-基礎'), `source_pdf`, and `title`.

    Returns:
        Domain Quiz entity populated with parsed questions.
    """
    variant = str(meta.get("variant", "1-基礎"))
    source_pdf = str(meta.get("source_pdf", ""))
    custom_title = str(meta.get("title", ""))
    quiz_title, questions_raw = _extract_title_and_raw_questions(raw_data, lecture_no, variant, custom_title)
    v_prefix = variant[:1] if variant else "1"
    id_prefix = f"{course_code}-{lecture_no:02d}-Q{v_prefix}"
    parsed = [
        q
        for idx, item in enumerate(questions_raw, start=1)
        if isinstance(item, dict)
        and (q := _parse_question_dict(item, id_prefix, idx, source_pdf)) is not None
    ]
    return Quiz(
        course_code=course_code,
        lecture_no=lecture_no,
        variant=variant,
        title=quiz_title,
        source_pdf=source_pdf,
        prompt_version="1.0",
        questions=parsed,
    )


def _normalize_stem(text: str) -> str:
    """Normalize question stem for duplicate comparison.

    Args:
        text: Question stem text.

    Returns:
        Normalized string with punctuation and whitespace removed.
    """
    return re.sub(r"[\s\W_]+", "", text).lower()


def _collect_unique_questions(quizzes: list[Quiz]) -> list[Question]:
    """Collect questions across quiz batches while filtering out duplicates.

    Args:
        quizzes: List of Quiz batches.

    Returns:
        Deduplicated list of questions.
    """
    seen_stems: set[str] = set()
    deduped: list[Question] = []
    for qz in quizzes:
        for q in qz.questions:
            norm = _normalize_stem(q.question)
            if norm and norm not in seen_stems:
                seen_stems.add(norm)
                deduped.append(q)
    return deduped


def _empty_quiz() -> Quiz:
    """Construct an empty placeholder Quiz entity when no batches exist.

    Returns:
        Empty Quiz entity with zero questions.
    """
    return Quiz(
        course_code="UNKNOWN",
        lecture_no=0,
        variant="1",
        title="Empty Quiz",
        source_pdf="",
        prompt_version="1.0",
        questions=[],
    )


def merge_and_deduplicate_quizzes(
    quizzes: list[Quiz],
    target_count: int = 30,
) -> tuple[Quiz, bool]:
    """Merge multiple Quiz batches, remove duplicate questions, and check target count.

    Args:
        quizzes: List of Quiz instances to combine.
        target_count: Target number of questions (default 30).

    Returns:
        A tuple of (merged_quiz, is_complete). If question count is less than target_count,
        is_complete will be False.
    """
    if not quizzes:
        return _empty_quiz(), False

    base = quizzes[0]
    deduped = _collect_unique_questions(quizzes)
    v_pfx = base.variant[:1] if base.variant else "1"
    reindexed = [
        replace(q, id=f"{base.course_code}-{base.lecture_no:02d}-Q{v_pfx}-{idx:03d}")
        for idx, q in enumerate(deduped[:target_count], start=1)
    ]
    merged = Quiz(
        course_code=base.course_code,
        lecture_no=base.lecture_no,
        variant=base.variant,
        title=base.title,
        source_pdf=base.source_pdf,
        prompt_version=base.prompt_version,
        questions=reindexed,
    )
    return merged, len(reindexed) >= target_count

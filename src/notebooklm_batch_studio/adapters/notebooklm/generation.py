"""Generation helpers shared by the NotebookLM adapter: language codes, quiz options, status checks.

notebooklm-py returns a `GenerationStatus` from every `generate_*` call. Its `task_id` is also the
artifact id, and a quota rejection usually comes back as a *failed status* rather than an
exception. These helpers make every generation pass the right language, check that status,
wait for completion, and hand back the artifact id so downloads and renames target exactly it.
Refs: ADR-004, ISSUE-003, ISSUE-004, ISSUE-005
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from notebooklm import (
    AudioFormat,
    AudioLength,
    GenerationStatus,
    InfographicDetail,
    InfographicOrientation,
    InfographicStyle,
    QuizDifficulty,
    QuizQuantity,
    SlideDeckFormat,
    SlideDeckLength,
    VideoFormat,
    VideoStyle,
)

from notebooklm_batch_studio.domain.exceptions import QuotaExceededError, StudioError
from notebooklm_batch_studio.domain.models import GenerationOptions

logger = logging.getLogger(__name__)

# notebooklm-py language codes (see notebooklm/_app/language.py); the library defaults to "en".
NLM_TRADITIONAL_CHINESE = "zh_Hant"
NLM_ENGLISH = "en"

QUIZ_DIFFICULTIES = {
    "easy": QuizDifficulty.EASY,
    "medium": QuizDifficulty.MEDIUM,
    "hard": QuizDifficulty.HARD,
}

DEFAULT_GENERATION_TIMEOUT = 900.0


def to_nlm_language(language: str) -> str:
    """Map a course language setting to a notebooklm-py output language code.

    Args:
        language: Course language ('zh-TW', 'en', 'bilingual').

    Returns:
        'en' for English courses, otherwise 'zh_Hant' (bilingual output is steered by instructions).
    """
    return NLM_ENGLISH if language == "en" else NLM_TRADITIONAL_CHINESE


def to_quiz_difficulty(difficulty: str | None) -> QuizDifficulty | None:
    """Map a domain difficulty string to the notebooklm-py enum.

    Args:
        difficulty: 'easy', 'medium', 'hard', or None for the NotebookLM default.

    Returns:
        QuizDifficulty value, or None.
    """
    return QUIZ_DIFFICULTIES.get(difficulty) if difficulty else None


def to_enum(enum_cls: type[Enum], value: str) -> Any:
    """Map a lower-case option string (e.g. 'portrait') to a notebooklm-py enum member.

    Args:
        enum_cls: notebooklm-py enum class.
        value: Lower-case member name stored in GenerationOptions.

    Returns:
        The matching enum member.
    """
    return enum_cls[value.upper()]


def _video_kwargs(o: GenerationOptions) -> dict[str, Any]:
    """Video arguments that respect notebooklm-py's rules for styles.

    Short (vertical) videos have a fixed style and accept no style text; a free-text style
    description requires `VideoStyle.CUSTOM`.

    Args:
        o: Effective generation options.

    Returns:
        Keyword arguments for `generate_video`.
    """
    if o.video_format == "short":
        return {"video_format": VideoFormat.SHORT, "video_style": VideoStyle.AUTO_SELECT}
    if o.video_style_prompt:
        return {
            "video_format": to_enum(VideoFormat, o.video_format),
            "video_style": VideoStyle.CUSTOM,
            "style_prompt": o.video_style_prompt,
        }
    return {
        "video_format": to_enum(VideoFormat, o.video_format),
        "video_style": to_enum(VideoStyle, o.video_style),
    }


def generation_kwargs(kind: str, options: GenerationOptions | None) -> dict[str, Any]:
    """Build the notebooklm-py keyword arguments for one artifact kind from course options.

    Args:
        kind: 'audio', 'infographic', 'slide_deck', 'video', 'quiz' or 'flashcards'.
        options: Course generation options (None = project defaults).

    Returns:
        Keyword arguments for the matching `client.artifacts.generate_*` call.
    """
    o = options or GenerationOptions()
    table: dict[str, dict[str, Any]] = {
        "audio": {
            "audio_format": to_enum(AudioFormat, o.audio_format),
            "audio_length": to_enum(AudioLength, o.audio_length),
        },
        "infographic": {
            "orientation": to_enum(InfographicOrientation, o.infographic_orientation),
            "detail_level": to_enum(InfographicDetail, o.infographic_detail),
            "style": to_enum(InfographicStyle, o.infographic_style),
        },
        "slide_deck": {
            "slide_format": to_enum(SlideDeckFormat, o.slide_format),
            "slide_length": to_enum(SlideDeckLength, o.slide_length),
        },
        "video": _video_kwargs(o),
        "quiz": {"quantity": to_enum(QuizQuantity, o.quiz_quantity)},
        "flashcards": {
            "quantity": to_enum(QuizQuantity, o.flashcards_quantity),
            "difficulty": to_enum(QuizDifficulty, o.flashcards_difficulty),
        },
    }
    return table.get(kind, {})


def _raise_for_status(status: GenerationStatus, label: str) -> None:
    """Raise a domain error when a generation status reports rejection or failure.

    Args:
        status: Status returned by a generate call or by polling.
        label: Human-readable artifact label for messages.

    Raises:
        QuotaExceededError: When NotebookLM rejected the request for quota / rate limit.
        StudioError: When generation failed for any other reason.
    """
    if status.is_rate_limited:
        raise QuotaExceededError(f"NotebookLM quota reached while generating {label}: {status.error}")
    if status.is_failed:
        raise StudioError(f"NotebookLM failed to generate {label}: {status.error or status.error_code}")


async def finish_generation(
    client: Any,
    notebook_id: str,
    status: GenerationStatus,
    label: str,
    timeout: float = DEFAULT_GENERATION_TIMEOUT,
) -> str:
    """Check a submitted generation, wait until it completes, and return its artifact id.

    Args:
        client: Open `NotebookLMClient` instance.
        notebook_id: Notebook identifier.
        status: Status returned by the `generate_*` call.
        label: Human-readable artifact label for logs and errors.
        timeout: Maximum seconds to wait for completion.

    Returns:
        The artifact id (equal to the generation task id).

    Raises:
        QuotaExceededError: When the request or the task was rejected for quota.
        StudioError: When the task failed.
    """
    _raise_for_status(status, label)
    logger.info("%s task %s submitted, waiting for completion", label, status.task_id)
    final = await client.artifacts.wait_for_completion(notebook_id, status.task_id, timeout=timeout)
    _raise_for_status(final, label)
    logger.info("%s task %s completed", label, status.task_id)
    return str(status.task_id)

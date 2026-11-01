"""Generation helpers shared by the NotebookLM adapter: language codes, quiz options, status checks.

notebooklm-py returns a `GenerationStatus` from every `generate_*` call. Its `task_id` is also the
artifact id, and a quota rejection usually comes back as a *failed status* rather than an
exception. These helpers make every generation pass the right language, check that status,
wait for completion, and hand back the artifact id so downloads and renames target exactly it.
Refs: ADR-004, ISSUE-003, ISSUE-004, ISSUE-005
"""

from __future__ import annotations

import logging
from typing import Any

from notebooklm import GenerationStatus, QuizDifficulty

from notebooklm_batch_studio.domain.exceptions import QuotaExceededError, StudioError

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

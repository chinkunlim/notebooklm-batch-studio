"""Error translation and language-instruction helpers for Gemini Notebook client calls."""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Coroutine, TypeVar

from notebooklm import ArtifactError, ArtifactParseError, ArtifactTimeoutError, AuthError, RateLimitError

from notebooklm_batch_studio.domain.exceptions import (
    AuthExpiredError,
    IncompleteArtifactError,
    QuotaExceededError,
    StudioError,
)

logger = logging.getLogger(__name__)

# Same directive notebooklm-py uses for its (web-disabled) Concept Explanation report format.
CONCEPT_EXPLANATION_DIRECTIVE = (
    "Explain the key concepts from the provided sources clearly and comprehensively. "
    "Define important terms, connect related ideas, use examples where helpful, and "
    "address common misconceptions."
)

T = TypeVar("T")


def build_language_instruction(base_prompt: str | None, language: str = "zh-TW") -> str:
    """Combine base prompt instructions with explicit language directives.

    Args:
        base_prompt: Optional base instructional prompt.
        language: Language code ('zh-TW', 'en', 'bilingual').

    Returns:
        Complete instructions string.
    """
    if language == "en":
        prefix = "Please generate all output strictly in English."
    elif language == "bilingual":
        prefix = (
            "Generate bilingual output in both English and Traditional Chinese. "
            "For all titles, questions, choices, key concepts, explanations, and flashcards, "
            "provide both English and Traditional Chinese (e.g. 'Concept / 概念')."
        )
    else:  # default zh-TW
        prefix = "請以繁體中文生成內容，專業學術名詞保留英文原名。"

    if base_prompt:
        return f"{prefix} {base_prompt}"
    return prefix


def map_provider_exception(err: Exception) -> Exception:
    """Map external provider errors into domain-specific exceptions.

    Args:
        err: Caught exception from Gemini Notebook client or network call.

    Returns:
        Mapped domain exception or the original error if unmapped.
    """
    if isinstance(err, StudioError):
        return err
    if isinstance(err, RateLimitError):
        logger.warning("Gemini Notebook Rate Limit exceeded: %s", err)
        return QuotaExceededError(
            message=f"Gemini Notebook API quota or rate limit reached: {err}", retry_after_seconds=3600
        )
    if isinstance(err, AuthError):
        logger.error("Gemini Notebook Authentication error: %s", err)
        return AuthExpiredError(f"Gemini Notebook credentials invalid or expired: {err}")
    if isinstance(err, FileNotFoundError) and "storage_state.json" in str(err):
        return AuthExpiredError("Authentication storage file not found. Please log in first.")
    if isinstance(err, (ArtifactTimeoutError, ArtifactParseError)):
        return IncompleteArtifactError(f"Artifact generation incomplete: {err}")
    if isinstance(err, ArtifactError):
        msg = str(err).lower()
        if "quota" in msg or "rate limit" in msg or "resource_exhausted" in msg:
            return QuotaExceededError(message=f"Gemini Notebook quota limit encountered: {err}")
        return StudioError(f"Gemini Notebook artifact operation failed: {err}")
    return _map_message_exception(err)


def _map_message_exception(err: Exception) -> Exception:
    """Infer quota or auth errors from generic exception message strings.

    Args:
        err: Caught unmapped exception.

    Returns:
        Mapped domain exception or original `err`.
    """
    err_msg = str(err).lower()
    if "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
        return QuotaExceededError(message=f"Gemini Notebook rate limit hit: {err}")
    if "401" in err_msg or "403" in err_msg or "unauthorized" in err_msg:
        return AuthExpiredError(f"Gemini Notebook authorization failed: {err}")
    return err


async def _raise_mapped_error(args: tuple[Any, ...], err: Exception) -> None:
    """Translate `err`, attach live retry delay if possible, and raise.

    Args:
        args: Positional call arguments (first item is inspected for `quota_retry_after`).
        err: Original exception caught during provider communication.

    Raises:
        StudioError: Translated domain exception or original error re-raised cleanly.
    """
    mapped = map_provider_exception(err)
    adapter = args[0] if args else None
    if (
        isinstance(mapped, QuotaExceededError)
        and adapter is not None
        and hasattr(adapter, "quota_retry_after")
    ):
        retry_after = await adapter.quota_retry_after()
        if retry_after is not None:
            mapped.retry_after_seconds = retry_after
    if mapped is not err:
        raise mapped from err
    if not isinstance(err, StudioError):
        logger.exception("Unexpected error communicating with Gemini Notebook: %s", err)
    raise err


def _translate_errors(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
    """Decorator to catch provider-specific exceptions and raise domain-specific errors.

    Args:
        func: The asynchronous adapter method to wrap.

    Returns:
        The wrapped asynchronous method.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        """Execute wrapped coroutine and translate any raised provider exceptions.

        Args:
            *args: Positional arguments for the wrapped method.
            **kwargs: Keyword arguments for the wrapped method.

        Returns:
            The return value of the wrapped coroutine.
        """
        try:
            return await func(*args, **kwargs)
        except Exception as err:
            await _raise_mapped_error(args, err)
            raise

    return wrapper

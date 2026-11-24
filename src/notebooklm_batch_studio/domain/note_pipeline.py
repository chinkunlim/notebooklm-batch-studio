"""Domain models, constants, and exceptions for modular Markdown note generation.

Supports dual generation backends (`gemini_web` primary and `notebooklm` fallback)
and preserves all semantic tags (`[核心]`, `{{定義:...}}`, `:::QEC`, etc.) in the
output `.md` files for downstream Phase 3 PDF rendering.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

# Maximum character length for a canned refusal reply from Gemini.
_MAX_REFUSAL_CHARS = 400

_REFUSAL_PATTERNS = re.compile(
    r"我只是一[个個]语言模型|我只是一[个個]語言模型|我是一[个個]文本\s*AI|超出了我的能力[范範][围圍]"
    r"|没法办到|沒辦法辦到|爱莫能助|愛莫能助"
    r"|I(?:'m| am) (?:just |only )?a (?:language model|text-based AI)"
    r"|I can(?:'|no)t help (?:you )?with that|I'm not able to help with that",
    re.IGNORECASE,
)

# Model menu name -> allowed keywords in Gemini response details ("Used ...").
MODEL_NAME_MAPPINGS: dict[str, list[str]] = {
    "4 Argon": ["4 Argon", "Argon"],
    "2.5 Pro": ["2.5 Pro", "Pro"],
    "3.1 Pro": ["3.1 Pro", "Pro"],
    "3.8 Flash": ["3.8 Flash", "Flash"],
    "3.5 Flash-Lite": ["3.5 Flash-Lite", "Flash-Lite"],
}


class NoteBackend(str, Enum):
    """Supported LLM backends for modular chapter note generation."""

    GEMINI_WEB = "gemini_web"
    NOTEBOOKLM = "notebooklm"


@dataclass(frozen=True)
class NotePipelineStep:
    """Definition of one modular note generation step.

    Attributes:
        step_id: Step identifier and output stem (e.g. `01_mindmap`).
        title: Human-readable Chinese title for the step.
        prompt_file: Filename inside `assets/prompts/modular_specs/`.
        required_tokens: Optional marker substrings checked during step validation.
        soft_fail: Whether failure of this step may be skipped during chapter stitching.
    """

    step_id: str
    title: str
    prompt_file: str
    required_tokens: tuple[str, ...] = ()
    soft_fail: bool = False


STANDARD_NOTE_STEPS: tuple[NotePipelineStep, ...] = (
    NotePipelineStep("01_mindmap", "心智圖與章節架構", "01_mindmap_spec.md", ("```flowchart",)),
    NotePipelineStep("02_outline", "詳細階層筆記", "02_outline_spec.md", ()),
    NotePipelineStep("03_qec", "QEC 深度理解框架", "03_qec_spec.md", (":::QEC",)),
    NotePipelineStep("04_cornell", "康乃爾筆記", "04_cornell_spec.md", ()),
    NotePipelineStep("05_matrix", "比較矩陣", "05_matrix_spec.md", ("|",), soft_fail=True),
    NotePipelineStep("06_feynman", "費曼技巧", "06_feynman_spec.md", ()),
    NotePipelineStep("07_quiz", "複習與課本題目", "07_quiz_spec.md", ()),
)


class NoteGenerationError(Exception):
    """Base exception for modular note generation pipeline errors."""


class QuotaExceededError(NoteGenerationError):
    """Raised when an LLM backend hits a usage quota or rate limit."""

    def __init__(
        self,
        message: str = "",
        raw_text: str | None = None,
        resume_after: datetime | None = None,
    ) -> None:
        """Initialize QuotaExceededError with optional reset timestamp.

        Args:
            message: Human-readable error summary.
            raw_text: Raw banner text from the backend UI.
            resume_after: Parsed UTC timestamp when quota is expected to reset.
        """
        super().__init__(message)
        self.raw_text = raw_text
        self.resume_after = resume_after


class DriverUnavailableError(NoteGenerationError, RuntimeError):
    """Raised when note generation is requested without an available backend driver."""


class PlaywrightStartupTimeoutError(DriverUnavailableError, TimeoutError):
    """Raised when Playwright browser startup stalls and is terminated by watchdog."""


class GenerationPausedError(NoteGenerationError):
    """Raised when generation stops cleanly in response to a user pause request."""


class ModelMismatchError(QuotaExceededError):
    """Raised when Gemini silently downgrades to a different model than requested."""

    def __init__(
        self,
        message: str = "",
        detected_model: str = "",
        resume_after: datetime | None = None,
    ) -> None:
        """Initialize ModelMismatchError with detected model information.

        Args:
            message: Error message.
            detected_model: Model name reported by Gemini UI.
            resume_after: Suggested cooldown timestamp.
        """
        super().__init__(message, raw_text=message, resume_after=resume_after)
        self.detected_model = detected_model


class GeminiRefusalError(QuotaExceededError):
    """Raised when Gemini responds with a short canned refusal instead of note content."""


def is_model_match(expected_model: str, detected_str: str) -> bool:
    """Check whether a detected model label matches the expected model name.

    Args:
        expected_model: Requested model name (e.g. `4 Argon`).
        detected_str: Text read from the Gemini model selector or response footer.

    Returns:
        True if any allowed keyword matches as a standalone token.
    """
    if not expected_model or not detected_str:
        return False
    allowed = MODEL_NAME_MAPPINGS.get(expected_model)
    if not allowed:
        return False
    return any(
        re.search(rf"(?<![\w-]){re.escape(keyword)}(?![\w-])", detected_str, re.IGNORECASE)
        for keyword in allowed
    )


def is_gemini_refusal(text: str) -> bool:
    """Return True when a reply is a short stock refusal rather than real note content.

    Args:
        text: Reply text returned by the model.

    Returns:
        True if the text is short and matches known refusal patterns.
    """
    stripped = (text or "").strip()
    if not stripped or len(stripped) > _MAX_REFUSAL_CHARS:
        return False
    return bool(_REFUSAL_PATTERNS.search(stripped))

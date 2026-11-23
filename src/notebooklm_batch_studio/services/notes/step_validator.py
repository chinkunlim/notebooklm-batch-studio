"""Step output validator for modular Markdown note generation (Refs: ADR-012).

Verifies that each step reply is non-empty, not a canned refusal, properly
terminated with `<!-- END -->`, balanced in KaTeX math delimiters, and contains
expected structural tokens.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Sequence

from notebooklm_batch_studio.domain.note_pipeline import is_gemini_refusal

logger = logging.getLogger(__name__)

END_TAG = "<!-- END -->"


@dataclass
class StepValidationResult:
    """Outcome of validating one module step reply.

    Attributes:
        is_valid: True when no blocking errors were found.
        errors: Blocking error messages.
        warnings: Non-blocking warnings.
        clean_markdown: Markdown with trailing `<!-- END -->` removed.
    """

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    clean_markdown: str = ""


def _strip_end_tag(content: str) -> tuple[str, bool]:
    """Remove trailing `<!-- END -->` tag and report whether it was present.

    Args:
        content: Raw reply text.

    Returns:
        Tuple of `(clean_text, has_end_tag)`.
    """
    if END_TAG not in content:
        return content.strip(), False
    idx = content.rfind(END_TAG)
    return content[:idx].rstrip(), True


def _check_math_balance(text: str) -> list[str]:
    """Check whether display math `$$` delimiters are balanced.

    Args:
        text: Markdown text without code blocks stripped.

    Returns:
        List of error messages (empty if balanced).
    """
    stripped = re.sub(r"```[\s\S]*?```", "", text)
    if stripped.count("$$") % 2 != 0:
        return ["KaTeX 展示數學區塊 `$$` 未成對閉合。"]
    return []


def validate_step_output(
    content: str,
    required_tokens: Sequence[str] = (),
    require_end_tag: bool = True,
) -> StepValidationResult:
    """Validate a single module step's Markdown output.

    Args:
        content: Raw reply text from Gemini Web or NotebookLM.
        required_tokens: Substrings that must appear in the reply (e.g. `:::QEC`).
        require_end_tag: Whether missing `<!-- END -->` is treated as an error.

    Returns:
        StepValidationResult with errors and cleaned Markdown.
    """
    errors: list[str] = []
    if not (content or "").strip():
        return StepValidationResult(is_valid=False, errors=["模型回傳空白內容。"], clean_markdown="")

    if is_gemini_refusal(content):
        return StepValidationResult(
            is_valid=False,
            errors=["模型回傳拒絕生成訊息（疑似觸發帳號或流量限制）。"],
            clean_markdown="",
        )

    clean_md, has_end = _strip_end_tag(content)
    if require_end_tag and not has_end:
        errors.append(f"缺少結束標記 {END_TAG}，輸出可能遭到截斷。")

    errors.extend(_check_math_balance(clean_md))
    for token in required_tokens:
        if token not in clean_md:
            errors.append(f"缺少必要結構標記：{token}")

    if errors:
        logger.warning("Step validation failed (%d errors): %s", len(errors), errors)
    return StepValidationResult(is_valid=len(errors) == 0, errors=errors, clean_markdown=clean_md)

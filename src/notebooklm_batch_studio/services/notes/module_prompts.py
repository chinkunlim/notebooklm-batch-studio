"""Modular Gemini prompt loader for Phase 1 Markdown note generation (Refs: ADR-012).

Reads standalone `.md` prompt files from `assets/prompts/modular_specs/*.md`
(or an optional override directory under `DATA_DIR/prompts/modular_specs/`) and
fills in `{{COURSE_NAME}}`, `{{CHAPTER_ID}}`, and `{{CHAPTER_TITLE}}`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from notebooklm_batch_studio.domain.note_pipeline import STANDARD_NOTE_STEPS

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PROMPT_DIR = PROJECT_ROOT / "assets" / "prompts" / "modular_specs"

MODULE_PROMPT_FILES: dict[str, str] = {step.step_id: step.prompt_file for step in STANDARD_NOTE_STEPS}

_PROMPT_BLOCK = re.compile(
    r"^## Gemini 提示詞[^\n]*\n.*?^````text\n(.*?)^````\s*$",
    re.DOTALL | re.MULTILINE,
)

_COMMON_OUTPUT_SUFFIX = (
    "\n\n【輸出結尾與格式提醒】\n"
    "- 核心定義與重點請標註課本頁碼 `(p.xx)`。\n"
    "- 回答最後一行請務必加上 `<!-- END -->`。\n"
)


@dataclass(frozen=True)
class StepPromptContext:
    """Chapter metadata substituted into a modular prompt template.

    Attributes:
        course: Course name replacing `{{COURSE_NAME}}`.
        chapter_id: Chapter identifier such as `ch01`, replacing `{{CHAPTER_ID}}`.
        chapter_title: Chapter title replacing `{{CHAPTER_TITLE}}`.
    """

    course: str
    chapter_id: str
    chapter_title: str = ""


class ModulePromptError(RuntimeError):
    """Raised when a prompt template file is missing or lacks a prompt block."""


def resolve_prompt_path(
    step_id: str,
    prompt_dir: Path | None = None,
    override_dir: Path | None = None,
) -> Path:
    """Resolve the Markdown prompt file for a step, preferring user override if present.

    Args:
        step_id: Step code such as `01_mindmap`.
        prompt_dir: Base directory containing bundled `modular_specs/*.md`.
        override_dir: Optional `DATA_DIR/prompts/modular_specs` override folder.

    Returns:
        Path to the `.md` prompt file.

    Raises:
        ModulePromptError: If `step_id` is unknown.
    """
    filename = MODULE_PROMPT_FILES.get(step_id)
    if not filename:
        raise ModulePromptError(f"未知的筆記模組步驟：{step_id}")
    if override_dir is not None:
        candidate = override_dir / filename
        if candidate.is_file():
            return candidate
    return (prompt_dir or DEFAULT_PROMPT_DIR) / filename


def extract_prompt_template(path: Path) -> str:
    """Read the raw prompt block under `## Gemini 提示詞` from a `.md` file.

    Args:
        path: Path to the modular spec `.md` file.

    Returns:
        Raw template string with placeholders intact.

    Raises:
        ModulePromptError: When the file cannot be read or lacks the fenced block.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot read module prompt %s: %s", path, exc)
        raise ModulePromptError(f"讀不到模組提示詞檔案：{path}") from exc
    match = _PROMPT_BLOCK.search(text)
    if match is None or not match.group(1).strip():
        logger.error("Missing '## Gemini 提示詞' block in %s", path)
        raise ModulePromptError(f"{path} 缺少「## Gemini 提示詞」區塊（````text ... ````）。")
    return match.group(1).strip()


def load_module_prompt(
    step_id: str,
    context: StepPromptContext,
    prompt_dir: Path | None = None,
    override_dir: Path | None = None,
) -> str:
    """Load a module prompt `.md` file and substitute chapter metadata.

    Args:
        step_id: Step code such as `02_outline`.
        context: Course and chapter values to fill in.
        prompt_dir: Optional custom directory for bundled prompt specs.
        override_dir: Optional override directory under `DATA_DIR`.

    Returns:
        Rendered prompt ready to send or copy for manual testing.
    """
    path = resolve_prompt_path(step_id, prompt_dir=prompt_dir, override_dir=override_dir)
    prompt = extract_prompt_template(path)
    for placeholder, value in (
        ("{{COURSE_NAME}}", context.course),
        ("{{CHAPTER_ID}}", context.chapter_id),
        ("{{CHAPTER_TITLE}}", context.chapter_title),
    ):
        prompt = prompt.replace(placeholder, value)
    if "<!-- END -->" not in prompt:
        prompt = prompt + _COMMON_OUTPUT_SUFFIX
    logger.debug("Loaded module prompt step=%s from %s (%d chars)", step_id, path.name, len(prompt))
    return prompt


def list_module_prompt_specs(
    prompt_dir: Path | None = None,
    override_dir: Path | None = None,
) -> list[dict[str, str]]:
    """List all standard modular prompt files and their resolved paths.

    Args:
        prompt_dir: Optional bundled prompt directory.
        override_dir: Optional user override directory.

    Returns:
        List of dicts describing `step_id`, `title`, `filename`, and `path`.
    """
    items: list[dict[str, str]] = []
    for step in STANDARD_NOTE_STEPS:
        resolved = resolve_prompt_path(step.step_id, prompt_dir=prompt_dir, override_dir=override_dir)
        items.append(
            {
                "step_id": step.step_id,
                "title": step.title,
                "filename": step.prompt_file,
                "path": str(resolved),
                "exists": "true" if resolved.is_file() else "false",
            }
        )
    return items

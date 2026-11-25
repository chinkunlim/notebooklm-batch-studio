"""Render the fixed Gemini Notebook "make me a site" prompt for one lecture or the whole book (SPEC-021)."""

from __future__ import annotations

import logging
from pathlib import Path

from notebooklm_batch_studio.domain.models import Course, Lecture

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEMPLATE = PROJECT_ROOT / "assets" / "prompts" / "notebook_site" / "learning_site.md"
SITE_TRIGGER = "make me a site"
DEFAULT_READER = "修這門課的學生，準備考試，並希望把概念用在實務"
_SECTION_A = "## A. 單一章節版"
_SECTION_B = "## B. 整本書／整門課版"
_BOOK_RANGE_SLOT = "{{書名或課程範圍，例如：第 1–17 章}}"


def _section(text: str, heading: str) -> str:
    """Cut one prompt section out of the template: from its heading to the next `---` line.

    Args:
        text: Full template text.
        heading: Section heading line, e.g. `## A. 單一章節版`.

    Returns:
        The section body without the heading, stripped.

    Raises:
        ValueError: When the heading is missing from the template.
    """
    start = text.find(heading)
    if start < 0:
        raise ValueError(f"learning-site template has no section {heading!r}")
    body = text[start + len(heading) :]
    lines = body.splitlines()
    end = next((i for i, line in enumerate(lines) if line.strip() == "---"), len(lines))
    return "\n".join(lines[:end]).strip()


def _book_range(course: Course) -> str:
    """Describe the lectures covered by a whole-book site, e.g. `第 1–17 講（共 10 講）`.

    Args:
        course: Course whose lectures are covered.

    Returns:
        Range text; just `全部講次` when the course has no lectures.
    """
    numbers = sorted(lec.no for lec in course.lectures)
    if not numbers:
        return "全部講次"
    return f"第 {numbers[0]}–{numbers[-1]} 講（共 {len(numbers)} 講）"


def render_site_prompt(
    course: Course, lecture: Lecture | None, extra: str | None = None, template: Path = DEFAULT_TEMPLATE
) -> str:
    """Build the chat prompt that makes Gemini Notebook generate a learning site.

    Args:
        course: Course the site belongs to (its name fills `{{課程名稱}}`).
        lecture: The lecture for a per-lecture site (section A), or None for the whole book (section B).
        extra: The job's custom prompt. One starting with `make me a site` is used as-is;
            any other non-empty text is appended as `補充要求`.
        template: Prompt template file (defaults to the bundled `learning_site.md`).

    Returns:
        Prompt text starting with `make me a site`.
    """
    extra = (extra or "").strip()
    if extra.startswith(SITE_TRIGGER):
        logger.info("learning-site prompt: using the job's full custom prompt course=%s", course.code)
        return extra
    text = template.read_text(encoding="utf-8")
    if lecture is None:
        prompt = _section(text, _SECTION_B).replace(_BOOK_RANGE_SLOT, _book_range(course))
    else:
        topic = lecture.topic.replace("-", " ").replace("_", " ").strip()
        prompt = _section(text, _SECTION_A).replace("{{講次}}", str(lecture.no)).replace("{{章名}}", topic)
    prompt = prompt.replace("{{課程名稱}}", course.name).replace("{{讀者}}", DEFAULT_READER)
    if extra:
        prompt = f"{prompt}\n\n補充要求：{extra}"
    logger.info(
        "learning-site prompt rendered course=%s lecture=%s chars=%d",
        course.code,
        lecture.no if lecture else "book",
        len(prompt),
    )
    return prompt

"""Domain generation options and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationOptions:
    """Per-course Gemini Notebook generation settings, stored as plain strings (mapped in the adapter).

    Each value is the lower-case name of a notebooklm-py enum member (e.g. 'portrait'), so the
    domain and services never import notebooklm-py. Refs: ADR-005

    Attributes:
        infographic_orientation: 'landscape', 'portrait' or 'square'.
        infographic_detail: 'concise', 'standard' or 'detailed'.
        infographic_style: 'auto_select', 'sketch_note', 'professional', 'bento_grid', 'editorial',
            'instructional', 'bricks', 'clay', 'anime', 'kawaii' or 'scientific'.
        audio_format: 'deep_dive', 'brief', 'critique' or 'debate'.
        audio_length: 'short', 'default' or 'long'.
        slide_format: 'detailed_deck' or 'presenter_slides'.
        slide_length: 'default' or 'short'.
        slide_download: 'pdf' or 'pptx'.
        video_format: 'explainer', 'brief', 'short' or 'cinematic'.
        video_style: 'auto_select', 'classic', 'whiteboard', 'kawaii', 'anime', 'watercolor',
            'retro_print', 'heritage' or 'paper_craft'.
        quiz_questions: Questions per lecture quiz (default 30); drives the prompt, the completeness
            check and Gemini Notebook's quantity setting together.
        flashcards_quantity: 'fewer', 'standard' or 'more'.
        flashcards_difficulty: 'easy', 'medium' or 'hard'.
        device_exports: Whether to fit infographics to A4 / iPad Air 4 / MacBook Pro 14.
        quiz_difficulty: 'auto' (each quiz keeps its own level: quiz 1 easy, 2 medium, 3 hard),
            or 'easy' / 'medium' / 'hard' to force one level.
        extra_instructions: Free text added to every prompt (course level) or to one output
            (job level), e.g. "the exam is mostly essays".
        video_style_prompt: Free-text visual style for videos (ignored for short videos).
        chapter_range: Lectures a course-wide output covers, e.g. "1-3" or "1,3,5-6"; empty = all.
        materials_as_source: Whether to upload `01 Materials` textbook PDFs as whole-course sources.
    """

    infographic_orientation: str = "portrait"
    infographic_detail: str = "detailed"
    infographic_style: str = "auto_select"
    audio_format: str = "deep_dive"
    audio_length: str = "default"
    slide_format: str = "detailed_deck"
    slide_length: str = "default"
    slide_download: str = "pdf"
    video_format: str = "explainer"
    video_style: str = "auto_select"
    quiz_questions: int = 30
    flashcards_quantity: str = "more"
    flashcards_difficulty: str = "medium"
    device_exports: bool = True
    quiz_difficulty: str = "auto"
    extra_instructions: str = ""
    video_style_prompt: str = ""
    chapter_range: str = ""
    materials_as_source: bool = False


# Allowed values per GenerationOptions field (None = boolean field).
GENERATION_OPTION_CHOICES: dict[str, tuple[str, ...] | None] = {
    "infographic_orientation": ("landscape", "portrait", "square"),
    "infographic_detail": ("concise", "standard", "detailed"),
    "infographic_style": (
        "auto_select",
        "sketch_note",
        "professional",
        "bento_grid",
        "editorial",
        "instructional",
        "bricks",
        "clay",
        "anime",
        "kawaii",
        "scientific",
    ),
    "audio_format": ("deep_dive", "brief", "critique", "debate"),
    "audio_length": ("short", "default", "long"),
    "slide_format": ("detailed_deck", "presenter_slides"),
    "slide_length": ("default", "short"),
    "slide_download": ("pdf", "pptx"),
    "video_format": ("explainer", "brief", "short", "cinematic"),
    "video_style": (
        "auto_select",
        "classic",
        "whiteboard",
        "kawaii",
        "anime",
        "watercolor",
        "retro_print",
        "heritage",
        "paper_craft",
    ),
    "flashcards_quantity": ("fewer", "standard", "more"),
    "flashcards_difficulty": ("easy", "medium", "hard"),
    "device_exports": None,
    "materials_as_source": None,
    "quiz_difficulty": ("auto", "easy", "medium", "hard"),
}

# Free-text options and their maximum length.
TEXT_OPTION_LIMITS: dict[str, int] = {"extra_instructions": 2000, "video_style_prompt": 300}

# Whole-number options and their allowed range.
NUMBER_OPTION_RANGES: dict[str, tuple[int, int]] = {"quiz_questions": (10, 60)}


def _validate_option_value(key: str, value: object) -> object:
    """Validate and normalize a single GenerationOptions field update.

    Args:
        key: Field name inside `GenerationOptions`.
        value: Candidate value to validate.

    Returns:
        Normalized field value ready for dataclass instantiation.

    Raises:
        ValueError: If `key` is unknown or `value` violates constraints.
    """
    if key in NUMBER_OPTION_RANGES:
        low, high = NUMBER_OPTION_RANGES[key]
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise ValueError(f"{key} must be a whole number from {low} to {high}")
        return value
    if key == "chapter_range":
        if not isinstance(value, str) or (value.strip() and parse_chapter_range(value) is None):
            raise ValueError('chapter_range must look like "1-3" or "1,3,5-6"')
        return value.replace(" ", "")
    if key in TEXT_OPTION_LIMITS:
        if not isinstance(value, str) or len(value) > TEXT_OPTION_LIMITS[key]:
            raise ValueError(f"{key} must be text of at most {TEXT_OPTION_LIMITS[key]} characters")
        return value.strip()
    if key not in GENERATION_OPTION_CHOICES:
        raise ValueError(f"Unknown generation option: {key}")
    choices = GENERATION_OPTION_CHOICES[key]
    if choices is None and not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false")
    if choices is not None and value not in choices:
        raise ValueError(f"{key} must be one of {', '.join(choices)}")
    return value


def merge_generation_options(base: GenerationOptions, changes: dict[str, object]) -> GenerationOptions:
    """Return new options with validated changes applied.

    Args:
        base: Current options.
        changes: Field name to new value.

    Returns:
        Updated GenerationOptions.

    Raises:
        ValueError: On an unknown field or a value outside the allowed choices.
    """
    values = dict(base.__dict__)
    for key, value in changes.items():
        values[key] = _validate_option_value(key, value)
    return GenerationOptions(**values)


def parse_chapter_range(text: str) -> set[int] | None:
    """Parse a lecture range such as "1-3" or "1,3,5-6".

    Args:
        text: Range text (spaces ignored).

    Returns:
        The lecture numbers, or None when the text is not a valid range.
    """
    numbers: set[int] = set()
    for part in text.replace(" ", "").split(","):
        bounds = part.split("-")
        if not part or len(bounds) > 2 or not all(b.isdigit() for b in bounds):
            return None
        low, high = int(bounds[0]), int(bounds[-1])
        if low < 1 or high < low:
            return None
        numbers.update(range(low, high + 1))
    return numbers


def effective_options(course_options: GenerationOptions, overrides: dict[str, object]) -> GenerationOptions:
    """Combine course options with one output's own overrides (SPEC-006).

    Overrides replace the course value field by field, except `extra_instructions`, where the
    output's text is added after the course's text so both apply.

    Args:
        course_options: The course's options.
        overrides: Validated per-output overrides (may be empty).

    Returns:
        Options to use for that output.
    """
    changes = dict(overrides)
    job_extra = str(changes.pop("extra_instructions", "") or "").strip()
    merged = merge_generation_options(course_options, changes)
    if job_extra:
        combined = "\n".join(t for t in (course_options.extra_instructions, job_extra) if t)
        merged = GenerationOptions(**{**merged.__dict__, "extra_instructions": combined})
    return merged

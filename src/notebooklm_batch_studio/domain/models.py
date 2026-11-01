"""Domain layer: pure data models, enums, and domain errors with zero I/O.

Defines the core entities for courses, lectures, artifacts, quizzes, flashcards,
mind maps, and the parallel queue state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ArtifactType(str, Enum):
    """Supported artifact types generated per lecture or course."""

    AUDIO = "audio"
    QUIZ_1 = "quiz_1"  # Legacy: Basic / Memory
    QUIZ_2 = "quiz_2"  # Legacy: Comprehension & Application
    QUIZ_3 = "quiz_3"  # Legacy: Exam Simulation
    QUIZ_ACADEMIC = "quiz_academic"  # Graduate / Senior Academic Advanced
    QUIZ_CONCEPT = "quiz_concept"  # Concept Drill / Exam Practice
    INFOGRAPHIC = "infographic"
    MIND_MAP = "mind_map"
    FLASHCARDS = "flashcards"
    STUDY_GUIDE = "study_guide"
    SLIDE_DECK = "slide_deck"
    DATA_TABLE = "data_table"
    VIDEO = "video"
    REPORTS_BRIEFING = "reports_briefing"
    REPORTS_STUDY_GUIDE = "reports_study_guide"
    REPORTS_BLOG_POST = "reports_blog_post"
    REPORTS_CONCEPT = "reports_concept_explanation"

    # Course-wide (Ch01-ChNN) aggregated artifacts
    COURSE_MOCK_EXAM = "course_mock_exam"  # Legacy Course-wide mock exam
    COURSE_QUIZ_ACADEMIC = "course_quiz_academic"  # Course-wide academic exam
    COURSE_QUIZ_CONCEPT = "course_quiz_concept"  # Course-wide concept drill
    COURSE_MIND_MAP = "course_mind_map"  # Course-wide mind map
    COURSE_AUDIO = "course_audio"  # Course-wide audio overview
    COURSE_STUDY_GUIDE = "course_study_guide"  # Course-wide study guide
    COURSE_SLIDE_DECK = "course_slide_deck"  # Course-wide slide deck
    COURSE_INFOGRAPHIC = "course_infographic"  # Course-wide infographic
    COURSE_DATA_TABLE = "course_data_table"  # Course-wide data table
    COURSE_VIDEO = "course_video"  # Course-wide cinematic video
    COURSE_REPORTS_BRIEFING = "course_reports_briefing"
    COURSE_REPORTS_STUDY_GUIDE = "course_reports_study_guide"
    COURSE_REPORTS_BLOG_POST = "course_reports_blog_post"
    COURSE_REPORTS_CONCEPT = "course_reports_concept_explanation"


class JobStatus(str, Enum):
    """Lifecycle states of an artifact generation task in the queue."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    QUOTA_WAIT = "quota_wait"
    SKIPPED = "skipped"
    NEEDS_REVIEW = "needs_review"


class ProfileName(str, Enum):
    """Predefined generation profiles for courses."""

    FULL = "full"
    QUIZ_ONLY = "quiz-only"
    EXAM_PREP = "exam-prep"


@dataclass(frozen=True)
class Choice:
    """A single multiple-choice answer option.

    Attributes:
        text: The option description.
        is_correct: Whether this choice is the correct answer.
        rationale: Pedagogical explanation of why this choice is right or wrong.
    """

    text: str
    is_correct: bool
    rationale: str = ""


@dataclass(frozen=True)
class Question:
    """A quiz question with multiple choices and learning context.

    Attributes:
        id: Unique identifier for the question (e.g. BIO101-03-Q2-001).
        question: The main question stem text.
        choices: List of 4 multiple-choice options.
        answer_index: Index (0-based) of the correct choice in `choices`.
        explanation: Detailed answer explanation for study review.
        source: Citation to lecture page or paragraph (e.g. p.12).
        hint: Optional contextual hint.
    """

    id: str
    question: str
    choices: list[Choice]
    answer_index: int
    explanation: str = ""
    source: str = ""
    hint: str = ""


@dataclass(frozen=True)
class Quiz:
    """A collection of questions forming a complete quiz variant.

    Attributes:
        course_code: Course identifier (e.g. BIO101).
        lecture_no: Lecture sequence number (e.g. 3).
        variant: Variant label (e.g. 1-基礎, 2-理解, 3-模擬考).
        title: Title of the quiz.
        source_pdf: Name of the original source PDF.
        prompt_version: Version identifier of the prompt used.
        questions: List of parsed questions (target: 30 questions).
    """

    course_code: str
    lecture_no: int
    variant: str
    title: str
    source_pdf: str
    prompt_version: str
    questions: list[Question] = field(default_factory=list)


@dataclass(frozen=True)
class Flashcard:
    """A study flashcard with front prompt and back answer.

    Attributes:
        front: The front text (concept, term, or question).
        back: The back text (definition, explanation, or answer).
        source: Optional source page citation.
    """

    front: str
    back: str
    source: str = ""


@dataclass(frozen=True)
class MindMapNode:
    """A node in a hierarchical mind map tree.

    Attributes:
        title: The topic or node heading.
        children: Subordinate concept nodes.
    """

    title: str
    children: list[MindMapNode] = field(default_factory=list)


@dataclass(frozen=True)
class Lecture:
    """A single lecture represented by one PDF source.

    Attributes:
        no: Sequence number (1, 2, ...).
        topic: Topic name inferred from filename or course.toml.
        filename: Name of the PDF file.
        sha256: SHA-256 hash of the PDF content for deduplication.
        source_id: Associated Gemini Notebook source ID once uploaded.
    """

    no: int
    topic: str
    filename: str
    sha256: str
    source_id: str | None = None
    upload_status: str = "pending"
    error_message: str | None = None


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
        video_format: 'explainer', 'brief' or 'short'.
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
    "video_format": ("explainer", "brief", "short"),
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
    "quiz_difficulty": ("auto", "easy", "medium", "hard"),
}

# Free-text options and their maximum length.
TEXT_OPTION_LIMITS: dict[str, int] = {"extra_instructions": 2000, "video_style_prompt": 300}

# Whole-number options and their allowed range.
NUMBER_OPTION_RANGES: dict[str, tuple[int, int]] = {"quiz_questions": (10, 60)}


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
        if key in NUMBER_OPTION_RANGES:
            low, high = NUMBER_OPTION_RANGES[key]
            if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
                raise ValueError(f"{key} must be a whole number from {low} to {high}")
            values[key] = value
            continue
        if key == "chapter_range":
            if not isinstance(value, str) or (value.strip() and parse_chapter_range(value) is None):
                raise ValueError('chapter_range must look like "1-3" or "1,3,5-6"')
            values[key] = value.replace(" ", "")
            continue
        if key in TEXT_OPTION_LIMITS:
            if not isinstance(value, str) or len(value) > TEXT_OPTION_LIMITS[key]:
                raise ValueError(f"{key} must be text of at most {TEXT_OPTION_LIMITS[key]} characters")
            values[key] = value.strip()
            continue
        if key not in GENERATION_OPTION_CHOICES:
            raise ValueError(f"Unknown generation option: {key}")
        choices = GENERATION_OPTION_CHOICES[key]
        if choices is None:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
        elif value not in choices:
            raise ValueError(f"{key} must be one of {', '.join(choices)}")
        values[key] = value
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


@dataclass(frozen=True)
class Course:
    """A course containing multiple lectures and generation settings.

    Attributes:
        code: Unique course identifier (e.g. BIO101).
        name: Full course title.
        source_dir: Filesystem path to the course's input materials.
        notebook_id: Associated Gemini Notebook notebook ID, if created.
        profile: Active generation profile.
        language: Target output language (default: zh-TW).
        exam_date: Optional exam date string (YYYY-MM-DD).
        watch: Whether folder watcher is enabled for this course.
        mock_exam_questions: Target question count for course-wide mock exam.
        lectures: List of lectures belonging to this course.
        generation_options: Gemini Notebook generation settings for this course.
        paused: When true, the queue does not start this course's jobs (set it up first).
        reuse_notebook: Reuse an existing Gemini Notebook notebook with the same title and its PDFs.
    """

    code: str
    name: str
    source_dir: str
    notebook_id: str | None = None
    profile: ProfileName = ProfileName.FULL
    language: str = "zh-TW"
    exam_date: str | None = None
    watch: bool = True
    mock_exam_questions: int = 50
    selected_chapter_artifacts: list[str] = field(default_factory=list)
    selected_course_artifacts: list[str] = field(default_factory=list)
    lectures: list[Lecture] = field(default_factory=list)
    generation_options: GenerationOptions = field(default_factory=GenerationOptions)
    paused: bool = False
    reuse_notebook: bool = True


def get_lecture_prefix(filename: str, fallback_no: int) -> str:
    """Infer prefix string like 'Ch01' or 'L01' from lecture filename.

    Args:
        filename: Lecture PDF filename.
        fallback_no: Fallback sequence number.

    Returns:
        Prefix string formatted as Ch01 or L01.
    """
    stem = filename.lower()
    if "ch" in stem or "chapter" in stem:
        return f"Ch{fallback_no:02d}"
    return f"L{fallback_no:02d}"


def get_course_range_prefix(lectures: list[Lecture]) -> str:
    """Calculate course-wide range prefix like 'Ch01-Ch06' or 'L01-L05'.

    Args:
        lectures: List of lectures in the course.

    Returns:
        Range string (e.g. 'Ch01-Ch06' or 'L01-L05').
    """
    if not lectures:
        return "All"
    first = lectures[0]
    last = lectures[-1]
    first_pre = get_lecture_prefix(first.filename, first.no)
    last_pre = get_lecture_prefix(last.filename, last.no)
    return f"{first_pre}-{last_pre}"


def get_artifact_english_title(artifact_type: ArtifactType | str, prefix: str) -> str:
    """Generate the standardized English title with prefix for Gemini Notebook in-app display.

    Args:
        artifact_type: Artifact type enum or string value.
        prefix: Prefix string such as 'Ch01', 'L01', or range 'Ch01-Ch06'.

    Returns:
        Formatted English title, e.g. '[Ch01] Quiz 1 - Fundamentals'.
    """
    type_val = artifact_type.value if isinstance(artifact_type, ArtifactType) else str(artifact_type)
    title_map = {
        ArtifactType.AUDIO.value: "Audio Overview",
        ArtifactType.QUIZ_1.value: "Quiz 1 - Fundamentals",
        ArtifactType.QUIZ_2.value: "Quiz 2 - Application",
        ArtifactType.QUIZ_3.value: "Quiz 3 - Practice Exam",
        ArtifactType.QUIZ_ACADEMIC.value: "Quiz - Academic Advanced",
        ArtifactType.QUIZ_CONCEPT.value: "Quiz - Concept Drill",
        ArtifactType.FLASHCARDS.value: "Flashcards",
        ArtifactType.MIND_MAP.value: "Mind Map",
        ArtifactType.STUDY_GUIDE.value: "Study Guide",
        ArtifactType.SLIDE_DECK.value: "Slide Deck",
        ArtifactType.INFOGRAPHIC.value: "Infographic",
        ArtifactType.DATA_TABLE.value: "Data Table",
        ArtifactType.VIDEO.value: "Video Overview",
        ArtifactType.REPORTS_BRIEFING.value: "Reports - Briefing Doc",
        ArtifactType.REPORTS_STUDY_GUIDE.value: "Reports - Study Guide",
        ArtifactType.REPORTS_BLOG_POST.value: "Reports - Blog Post",
        ArtifactType.REPORTS_CONCEPT.value: "Reports - Concept Explanation",
        ArtifactType.COURSE_MOCK_EXAM.value: "Comprehensive Mock Exam",
        ArtifactType.COURSE_QUIZ_ACADEMIC.value: "Comprehensive Mock Exam - Academic Advanced",
        ArtifactType.COURSE_QUIZ_CONCEPT.value: "Comprehensive Mock Exam - Concept Drill",
        ArtifactType.COURSE_MIND_MAP.value: "Course Mind Map",
        ArtifactType.COURSE_STUDY_GUIDE.value: "Synthesis Study Guide",
        ArtifactType.COURSE_AUDIO.value: "Course Audio Overview",
        ArtifactType.COURSE_SLIDE_DECK.value: "Summary Slide Deck",
        ArtifactType.COURSE_INFOGRAPHIC.value: "Comprehensive Infographic",
        ArtifactType.COURSE_DATA_TABLE.value: "Master Data Table",
        ArtifactType.COURSE_VIDEO.value: "Course Video Overview",
        ArtifactType.COURSE_REPORTS_BRIEFING.value: "Course Reports - Briefing Doc",
        ArtifactType.COURSE_REPORTS_STUDY_GUIDE.value: "Course Reports - Synthesis Study Guide",
        ArtifactType.COURSE_REPORTS_BLOG_POST.value: "Course Reports - Blog Post",
        ArtifactType.COURSE_REPORTS_CONCEPT.value: "Course Reports - Concept Explanation",
    }
    label = title_map.get(type_val, type_val.replace("_", " ").title())
    return f"[{prefix}] {label}"


@dataclass(frozen=True)
class ArtifactJob:
    """A scheduled task in the parallel generation queue.

    Attributes:
        id: Unique task identifier (UUID string).
        course_code: Course identifier.
        lecture_no: Sequence number of the lecture, or None for course-wide tasks.
        artifact_type: The type of artifact to generate.
        status: Current lifecycle state.
        attempts: Number of execution attempts.
        worker_id: Identifier of the worker currently processing this task.
        error_message: Failure reason if status is FAILED.
        output_file: Filesystem path of the generated artifact once completed.
        quota_blocked_at: Timestamp when daily quota limit was hit.
        cooldown_until: Timestamp when this task is eligible for quota resume probe.
        created_at: Task creation timestamp.
        updated_at: Last state transition timestamp.
        version: 1 for the first generation; 2, 3, ... for each regeneration (ADR-005).
        artifact_ids: Gemini Notebook artifact / note ids this job produced.
    """

    id: str
    course_code: str
    lecture_no: int | None
    artifact_type: ArtifactType
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    worker_id: str | None = None
    error_message: str | None = None
    output_file: str | None = None
    custom_prompt: str | None = None
    style_options: str | None = None
    interactive_path: str | None = None
    source_origin: str = "auto"
    quota_blocked_at: datetime | None = None
    cooldown_until: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = 1
    artifact_ids: tuple[str, ...] = ()


@dataclass
class QuizMistake:
    """A single wrong question record from a student quiz attempt.

    Attributes:
        id: Unique identifier.
        attempt_id: Identifier of the parent attempt.
        course_code: Course identifier.
        lecture_no: Lecture sequence number or None for course-wide.
        question_text: Full text of the question.
        choices: List of choice strings.
        correct_index: Index of the correct choice.
        selected_index: Index of the student's selected choice.
        explanation: Detailed academic rationale.
        is_resolved: Whether the question has been resolved.
        created_at: Creation timestamp.
        confidence: How sure the student was ('sure', 'unsure', 'guess'), or None if not rated.
    """

    id: str
    attempt_id: str
    course_code: str
    lecture_no: int | None
    question_text: str
    choices: list[str]
    correct_index: int
    selected_index: int
    explanation: str
    is_resolved: bool = False
    created_at: datetime | None = None
    confidence: str | None = None


@dataclass
class QuizAttempt:
    """A record of a completed quiz submission by a student.

    Attributes:
        id: Unique identifier.
        course_code: Course identifier.
        lecture_no: Lecture sequence number or None for course-wide.
        quiz_variant: Variant of quiz (e.g. academic, concept).
        score: Score achieved.
        total_questions: Total number of questions.
        created_at: Submission timestamp.
        mistakes: Optional list of mistake entities recorded during this attempt.
        confidence_summary: Counts from the confidence ratings, e.g. {"sure_wrong": 2, "guess_right": 3}.
    """

    id: str
    course_code: str
    lecture_no: int | None
    quiz_variant: str
    score: int
    total_questions: int
    created_at: datetime | None = None
    mistakes: list[QuizMistake] = field(default_factory=list)
    confidence_summary: dict[str, int] | None = None

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
    QUIZ_1 = "quiz_1"  # Basic / Memory
    QUIZ_2 = "quiz_2"  # Comprehension & Application
    QUIZ_3 = "quiz_3"  # Exam Simulation
    INFOGRAPHIC = "infographic"
    MIND_MAP = "mind_map"
    FLASHCARDS = "flashcards"
    STUDY_GUIDE = "study_guide"
    SLIDE_DECK = "slide_deck"
    DATA_TABLE = "data_table"
    VIDEO = "video"

    # Course-wide (Ch01-ChNN) aggregated artifacts
    COURSE_MOCK_EXAM = "course_mock_exam"  # Course-wide mock exam
    COURSE_MIND_MAP = "course_mind_map"  # Course-wide mind map
    COURSE_AUDIO = "course_audio"  # Course-wide audio overview
    COURSE_STUDY_GUIDE = "course_study_guide"  # Course-wide study guide
    COURSE_SLIDE_DECK = "course_slide_deck"  # Course-wide slide deck
    COURSE_INFOGRAPHIC = "course_infographic"  # Course-wide infographic
    COURSE_DATA_TABLE = "course_data_table"  # Course-wide data table
    COURSE_VIDEO = "course_video"  # Course-wide cinematic video


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
        source_id: Associated NotebookLM source ID once uploaded.
    """

    no: int
    topic: str
    filename: str
    sha256: str
    source_id: str | None = None
    upload_status: str = "pending"
    error_message: str | None = None


@dataclass(frozen=True)
class Course:
    """A course containing multiple lectures and generation settings.

    Attributes:
        code: Unique course identifier (e.g. BIO101).
        name: Full course title.
        source_dir: Filesystem path to the course's input materials.
        notebook_id: Associated NotebookLM notebook ID, if created.
        profile: Active generation profile.
        language: Target output language (default: zh-TW).
        exam_date: Optional exam date string (YYYY-MM-DD).
        watch: Whether folder watcher is enabled for this course.
        mock_exam_questions: Target question count for course-wide mock exam.
        lectures: List of lectures belonging to this course.
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
    """Generate the standardized English title with prefix for NotebookLM in-app display.

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
        ArtifactType.FLASHCARDS.value: "Flashcards",
        ArtifactType.MIND_MAP.value: "Mind Map",
        ArtifactType.STUDY_GUIDE.value: "Study Guide",
        ArtifactType.SLIDE_DECK.value: "Slide Deck",
        ArtifactType.INFOGRAPHIC.value: "Infographic",
        ArtifactType.DATA_TABLE.value: "Data Table",
        ArtifactType.VIDEO.value: "Video Overview",
        ArtifactType.COURSE_MOCK_EXAM.value: "Comprehensive Mock Exam",
        ArtifactType.COURSE_MIND_MAP.value: "Course Mind Map",
        ArtifactType.COURSE_STUDY_GUIDE.value: "Synthesis Study Guide",
        ArtifactType.COURSE_AUDIO.value: "Course Audio Overview",
        ArtifactType.COURSE_SLIDE_DECK.value: "Summary Slide Deck",
        ArtifactType.COURSE_INFOGRAPHIC.value: "Comprehensive Infographic",
        ArtifactType.COURSE_DATA_TABLE.value: "Master Data Table",
        ArtifactType.COURSE_VIDEO.value: "Course Video Overview",
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
    quota_blocked_at: datetime | None = None
    cooldown_until: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# Backward-compatibility for initial bootstrap tests
@dataclass(frozen=True)
class GreetingRequest:
    """A request to greet one user."""

    user_name: str


@dataclass(frozen=True)
class GreetingResult:
    """The greeting produced by the service layer."""

    message: str
    environment: str

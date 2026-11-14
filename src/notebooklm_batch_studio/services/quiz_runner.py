"""Quiz and mock exam execution runner extracted from ArtifactRunner."""

from __future__ import annotations

import dataclasses
import json
import logging
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from notebooklm_batch_studio.domain.exceptions import AuthExpiredError, NeedsReviewError, QuotaExceededError
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    GenerationOptions,
    Quiz,
)
from notebooklm_batch_studio.domain.naming import versioned_name
from notebooklm_batch_studio.domain.repositories import NotebookLMClientProtocol
from notebooklm_batch_studio.services.converters.quiz_converter import (
    merge_and_deduplicate_quizzes,
    parse_notebooklm_quiz,
    to_answer_markdown,
    to_exam_markdown,
    to_interactive_html,
    to_pdf,
)
from notebooklm_batch_studio.services.converters.quiz_converter import (
    to_json as quiz_to_json,
)

logger = logging.getLogger(__name__)

# A processed job: primary output path plus the Gemini Notebook artifact ids it produced.
ProcessResult = tuple[str, list[str]]

QUIZ_TYPES = (
    ArtifactType.QUIZ_1,
    ArtifactType.QUIZ_2,
    ArtifactType.QUIZ_3,
    ArtifactType.QUIZ_ACADEMIC,
    ArtifactType.QUIZ_CONCEPT,
)
MOCK_EXAM_TYPES = (
    ArtifactType.COURSE_MOCK_EXAM,
    ArtifactType.COURSE_QUIZ_ACADEMIC,
    ArtifactType.COURSE_QUIZ_CONCEPT,
)
QUIZ_VARIANTS = {
    ArtifactType.QUIZ_1: ("1-基礎", "easy"),
    ArtifactType.QUIZ_2: ("2-理解", "medium"),
    ArtifactType.QUIZ_3: ("3-模擬考", "hard"),
    ArtifactType.QUIZ_ACADEMIC: ("學術精研", "hard"),
    ArtifactType.QUIZ_CONCEPT: ("概念刷題", "medium"),
}


@dataclasses.dataclass(frozen=True)
class JobTarget:
    """Resolved Gemini Notebook notebook target, sources, and output folder for a job."""

    nb_id: str
    source_ids: list[str]
    out_dir: Path


@dataclasses.dataclass(frozen=True)
class _BatchSpec:
    """Parameters governing multi-batch quiz or mock-exam generation."""

    attempts: int
    target_count: int
    lecture_no: int
    variant: str
    difficulty: str | None
    options: GenerationOptions
    source_pdf: str = ""
    title: str = ""
    default_prompt_prefix: str = "Comprehensive final exam batch"


RenameCallback = Callable[[ArtifactJob, Course, str, list[str]], Awaitable[None]]


def save_quiz_files(out_dir: Path, quiz: Quiz, file_prefix: str = "") -> str:
    """Save quiz markdown, JSON, interactive HTML, and PDF files to target directory.

    Args:
        out_dir: Destination folder.
        quiz: Domain Quiz entity.
        file_prefix: Optional prefix to prevent overwriting between variants.

    Returns:
        Path string of primary quiz.json.
    """
    prefix = f"{file_prefix}_" if file_prefix and not file_prefix.endswith("_") else file_prefix
    (out_dir / f"{prefix}題目卷.md").write_text(to_exam_markdown(quiz), encoding="utf-8")
    (out_dir / f"{prefix}答案卷.md").write_text(to_answer_markdown(quiz), encoding="utf-8")
    final_json = out_dir / f"{prefix}quiz.json"
    final_json.write_text(quiz_to_json(quiz), encoding="utf-8")
    (out_dir / f"{prefix}interactive_quiz.html").write_text(to_interactive_html(quiz), encoding="utf-8")
    to_pdf(quiz, out_dir / f"{prefix}題目卷.pdf", is_answer_key=False)
    to_pdf(quiz, out_dir / f"{prefix}答案卷.pdf", is_answer_key=True)

    compat_json = out_dir / "quiz.json"
    if not compat_json.exists():
        compat_json.write_text(quiz_to_json(quiz), encoding="utf-8")
    compat_ans_md = out_dir / "答案卷.md"
    if not compat_ans_md.exists():
        compat_ans_md.write_text(to_answer_markdown(quiz), encoding="utf-8")
    return str(final_json)


async def generate_quiz_batch(
    client: NotebookLMClientProtocol, target: JobTarget, spec: _BatchSpec, prompt_and_path: tuple[str, Path]
) -> tuple[str, dict[str, object] | None]:
    """Generate one quiz batch and download exactly that artifact.

    Args:
        client: Gemini Notebook client protocol.
        target: Resolved notebook target and source IDs.
        spec: Batch generation specification.
        prompt_and_path: Tuple of `(prompt, tmp_json_path)`.

    Returns:
        Generated artifact id and the raw quiz JSON (None if nothing was downloaded).
    """
    prompt, tmp_json = prompt_and_path
    art_id = await client.generate_quiz(
        target.nb_id, target.source_ids, prompt=prompt, difficulty=spec.difficulty, options=spec.options
    )
    await client.download_quiz(target.nb_id, str(tmp_json), artifact_id=art_id)
    raw = json.loads(tmp_json.read_text(encoding="utf-8")) if tmp_json.exists() else None
    return art_id, raw


async def quarantine_quiz(
    needs_review_dir: Path,
    rename_cb: RenameCallback,
    job: ArtifactJob,
    ctx: tuple[Course, str, list[str], Quiz, int],
) -> None:
    """Rename attempts, save an incomplete quiz under `needs_review/`, and raise.

    Args:
        needs_review_dir: Base quarantine folder from config.
        rename_cb: Coroutine renaming artifacts on Gemini Notebook.
        job: Current artifact job.
        ctx: Tuple of `(course, nb_id, art_ids, merged_quiz, target_count)`.

    Raises:
        NeedsReviewError: Always; carries the quarantined JSON path.
    """
    course, nb_id, art_ids, quiz, target_count = ctx
    prefix = versioned_name(job.artifact_type.value, job.version)
    scope = "course" if job.lecture_no is None else f"L{job.lecture_no}"
    await rename_cb(job, course, nb_id, art_ids)
    review_dir = needs_review_dir / f"{course.code}_{scope}_{prefix}"
    review_dir.mkdir(parents=True, exist_ok=True)
    incomplete_json = review_dir / f"{prefix}_quiz.json"
    incomplete_json.write_text(quiz_to_json(quiz), encoding="utf-8")
    count = len(quiz.questions)
    logger.warning("Quiz incomplete (%d/%d questions), quarantined to %s", count, target_count, review_dir)
    raise NeedsReviewError(f"Quiz has {count}/{target_count} questions", output_file=str(incomplete_json))


async def _run_single_quiz_attempt(
    client: NotebookLMClientProtocol,
    course: Course,
    target: JobTarget,
    ctx: tuple[_BatchSpec, str | None, Path, int],
) -> tuple[str, Quiz | None]:
    """Generate and parse one quiz batch attempt into a Quiz entity.

    Args:
        client: Gemini Notebook client protocol.
        course: Course domain entity.
        target: Resolved notebook target and sources.
        ctx: Tuple of `(_BatchSpec, custom_prompt, temp_dir_path, attempt_index)`.

    Returns:
        Tuple of `(artifact_id, parsed_quiz_or_none)`.
    """
    spec, custom_prompt, tmp_dir, attempt = ctx
    tmp_json = tmp_dir / f"attempt_{attempt}.json"
    prompt = custom_prompt or (
        f"{spec.default_prompt_prefix} {attempt + 1}, target={spec.target_count}, language={course.language}"
    )
    art_id, raw = await generate_quiz_batch(client, target, spec, (prompt, tmp_json))
    if raw is None:
        return art_id, None
    quiz = parse_notebooklm_quiz(
        raw, course.code, spec.lecture_no, variant=spec.variant, source_pdf=spec.source_pdf, title=spec.title
    )
    return art_id, quiz


async def _try_single_quiz_attempt(
    client: NotebookLMClientProtocol,
    course: Course,
    target: JobTarget,
    ctx: tuple[_BatchSpec, str | None, Path, int],
) -> tuple[tuple[str, Quiz | None] | None, Exception | None]:
    """Run one quiz generation attempt, swallowing transient errors for retry.

    Args:
        client: Gemini Notebook client protocol.
        course: Course domain entity.
        target: Resolved notebook target and sources.
        ctx: Tuple of `(_BatchSpec, custom_prompt, tmp_dir_path, attempt_index)`.

    Returns:
        Tuple of `((artifact_id, quiz) or None, captured_error or None)`.
    """
    spec, _, _, attempt = ctx
    try:
        return await _run_single_quiz_attempt(client, course, target, ctx), None
    except (QuotaExceededError, AuthExpiredError):
        raise
    except Exception as err:
        logger.warning("Quiz batch attempt %d/%d failed: %s", attempt + 1, spec.attempts, err)
        return None, err


async def _collect_batches(
    client: NotebookLMClientProtocol,
    course: Course,
    target: JobTarget,
    spec_and_prompt: tuple[_BatchSpec, str | None],
) -> tuple[list[Quiz], list[str]]:
    """Run repeated quiz generation attempts until target question count or cap is reached.

    Args:
        client: Gemini Notebook client protocol.
        course: Course domain entity.
        target: Resolved notebook target and sources.
        spec_and_prompt: Tuple of `(_BatchSpec, custom_prompt)`.

    Returns:
        Tuple of `(parsed_quiz_batches, artifact_ids)`.
    """
    spec, custom_prompt = spec_and_prompt
    batches: list[Quiz] = []
    art_ids: list[str] = []
    last_err: Exception | None = None
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        for attempt in range(spec.attempts):
            res, err = await _try_single_quiz_attempt(
                client, course, target, (spec, custom_prompt, tmp_path, attempt)
            )
            if err is not None:
                last_err = err
                continue
            if res is None:
                continue
            art_ids.append(res[0])
            if res[1] is not None:
                batches.append(res[1])
            if merge_and_deduplicate_quizzes(batches, target_count=spec.target_count)[1]:
                break
    if not batches and last_err is not None:
        raise last_err
    return batches, art_ids


def _mock_exam_title(course_code: str, art_type: ArtifactType) -> str:
    """Resolve standardized Chinese title for a course-wide mock exam artifact type.

    Args:
        course_code: Course identifier.
        art_type: Mock exam artifact enum variant.

    Returns:
        Formatted quiz title string.
    """
    if art_type == ArtifactType.COURSE_QUIZ_ACADEMIC:
        return f"[{course_code}] 全課程學術精研期末考"
    if art_type == ArtifactType.COURSE_QUIZ_CONCEPT:
        return f"[{course_code}] 全課程核心觀念刷題考"
    return f"[{course_code}] 全課程期末模擬考"


class QuizRunner:
    """Executes lecture quiz and course mock-exam generation with deduplication and quarantine."""

    def __init__(
        self,
        notebooklm_client: NotebookLMClientProtocol,
        needs_review_dir: Path,
        rename_cb: RenameCallback,
    ) -> None:
        """Initialize the quiz runner.

        Args:
            notebooklm_client: Gemini Notebook protocol client.
            needs_review_dir: Quarantine root directory for short quizzes.
            rename_cb: Coroutine renaming artifacts on Gemini Notebook.
        """
        self.notebooklm_client = notebooklm_client
        self.needs_review_dir = needs_review_dir
        self.rename_cb = rename_cb

    async def process_quiz(self, job: ArtifactJob, course: Course, target: JobTarget) -> ProcessResult:
        """Generate a 30-question quiz at the variant's difficulty, with dedup, markdown, and PDF.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            target: Resolved Gemini Notebook target and output directory.

        Returns:
            Path to resulting quiz.json and generated artifact ids.

        Raises:
            NeedsReviewError: When fewer than target questions were collected.
        """
        variant, difficulty = QUIZ_VARIANTS.get(job.artifact_type, ("1-基礎", None))
        if course.generation_options.quiz_difficulty != "auto":
            difficulty = course.generation_options.quiz_difficulty
        target_count = course.generation_options.quiz_questions
        spec = _BatchSpec(
            attempts=4,
            target_count=target_count,
            lecture_no=job.lecture_no or 0,
            variant=variant,
            difficulty=difficulty,
            options=course.generation_options,
            source_pdf=f"{job.lecture_no:02d}.pdf",
            default_prompt_prefix=f"Generate rigorous questions for {variant} attempt",
        )
        batches, art_ids = await _collect_batches(
            self.notebooklm_client, course, target, (spec, job.custom_prompt)
        )
        merged, is_complete = merge_and_deduplicate_quizzes(batches, target_count=target_count)
        if not is_complete:
            ctx = (course, target.nb_id, art_ids, merged, target_count)
            await quarantine_quiz(self.needs_review_dir, self.rename_cb, job, ctx)
        prefix = versioned_name(job.artifact_type.value, job.version)
        return save_quiz_files(target.out_dir, merged, file_prefix=prefix), art_ids

    async def process_mock_exam(self, job: ArtifactJob, course: Course, target: JobTarget) -> ProcessResult:
        """Generate course-wide mock exam across all lecture sources.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            target: Resolved Gemini Notebook target and output directory.

        Returns:
            Path to resulting quiz.json and generated artifact ids.

        Raises:
            NeedsReviewError: When fewer than target questions were collected.
        """
        target_q = course.mock_exam_questions or 50
        forced = course.generation_options.quiz_difficulty
        # Gemini Notebook's size setting follows the mock exam target, not the lecture quiz count.
        mock_options = dataclasses.replace(course.generation_options, quiz_questions=min(target_q, 60))
        spec = _BatchSpec(
            attempts=6,
            target_count=target_q,
            lecture_no=0,
            variant="模擬考",
            difficulty=None if forced == "auto" else forced,
            options=mock_options,
            title=_mock_exam_title(course.code, job.artifact_type),
        )
        batches, art_ids = await _collect_batches(
            self.notebooklm_client, course, target, (spec, job.custom_prompt)
        )
        final_quiz, is_complete = merge_and_deduplicate_quizzes(batches, target_count=target_q)
        if not is_complete:  # Refs: ISSUE-009
            ctx = (course, target.nb_id, art_ids, final_quiz, target_q)
            await quarantine_quiz(self.needs_review_dir, self.rename_cb, job, ctx)
        prefix = versioned_name(job.artifact_type.value, job.version)
        return save_quiz_files(target.out_dir, final_quiz, file_prefix=prefix), art_ids

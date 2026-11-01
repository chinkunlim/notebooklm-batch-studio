"""Artifact runner: executes generation, conversion, and in-app renaming for artifacts.

Extracted from orchestrator to maintain modular single-responsibility and respect
strict file length boundaries.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from notebooklm_batch_studio.config.settings import AppConfig, load_config
from notebooklm_batch_studio.domain.exceptions import NeedsReviewError
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    GenerationOptions,
    Quiz,
    get_artifact_english_title,
    get_course_range_prefix,
    get_lecture_prefix,
)
from notebooklm_batch_studio.domain.naming import versioned_name, versioned_title
from notebooklm_batch_studio.domain.repositories import NotebookLMClientProtocol
from notebooklm_batch_studio.services.converters.flashcard_converter import (
    parse_notebooklm_flashcards,
    to_anki_csv,
)
from notebooklm_batch_studio.services.converters.flashcard_converter import (
    to_json as flashcards_to_json,
)
from notebooklm_batch_studio.services.converters.image_fitter import export_device_versions
from notebooklm_batch_studio.services.converters.mindmap_converter import (
    parse_notebooklm_mindmap,
    to_opml,
)
from notebooklm_batch_studio.services.converters.mindmap_converter import (
    to_json as mindmap_to_json,
)
from notebooklm_batch_studio.services.converters.mindmap_converter import (
    to_markdown as mindmap_to_markdown,
)
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


def _save_quiz_files(out_dir: Path, quiz: Quiz, file_prefix: str = "") -> str:
    """Save quiz markdown, JSON, interactive HTML, and PDF files to target directory.

    Args:
        out_dir: Destination folder.
        quiz: Domain Quiz entity.
        file_prefix: Optional prefix to prevent overwriting between variants.

    Returns:
        Path string of primary quiz.json.
    """
    prefix = f"{file_prefix}_" if file_prefix and not file_prefix.endswith("_") else file_prefix
    exam_md = out_dir / f"{prefix}題目卷.md"
    ans_md = out_dir / f"{prefix}答案卷.md"
    final_json = out_dir / f"{prefix}quiz.json"
    interactive_html = out_dir / f"{prefix}interactive_quiz.html"
    exam_pdf = out_dir / f"{prefix}題目卷.pdf"
    ans_pdf = out_dir / f"{prefix}答案卷.pdf"

    exam_md.write_text(to_exam_markdown(quiz), encoding="utf-8")
    ans_md.write_text(to_answer_markdown(quiz), encoding="utf-8")
    final_json.write_text(quiz_to_json(quiz), encoding="utf-8")
    interactive_html.write_text(to_interactive_html(quiz), encoding="utf-8")
    to_pdf(quiz, exam_pdf, is_answer_key=False)
    to_pdf(quiz, ans_pdf, is_answer_key=True)

    compat_json = out_dir / "quiz.json"
    if not compat_json.exists():
        compat_json.write_text(quiz_to_json(quiz), encoding="utf-8")
    compat_ans_md = out_dir / "答案卷.md"
    if not compat_ans_md.exists():
        compat_ans_md.write_text(to_answer_markdown(quiz), encoding="utf-8")

    return str(final_json)


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
REPORT_FORMATS = {
    ArtifactType.REPORTS_BRIEFING: "briefing_doc",
    ArtifactType.COURSE_REPORTS_BRIEFING: "briefing_doc",
    ArtifactType.REPORTS_STUDY_GUIDE: "study_guide",
    ArtifactType.COURSE_REPORTS_STUDY_GUIDE: "study_guide",
    ArtifactType.REPORTS_BLOG_POST: "blog_post",
    ArtifactType.COURSE_REPORTS_BLOG_POST: "blog_post",
}
QUIZ_VARIANTS = {
    ArtifactType.QUIZ_1: ("1-基礎", "easy"),
    ArtifactType.QUIZ_2: ("2-理解", "medium"),
    ArtifactType.QUIZ_3: ("3-模擬考", "hard"),
    ArtifactType.QUIZ_ACADEMIC: ("學術精研", "hard"),
    ArtifactType.QUIZ_CONCEPT: ("概念刷題", "medium"),
}
# Single-shot artifacts: downloader kind, lecture filename, course-wide filename
SIMPLE_OUTPUTS: dict[ArtifactType, tuple[str, str, str]] = {
    ArtifactType.STUDY_GUIDE: ("report", "study_guide.md", "course_study_guide.md"),
    ArtifactType.COURSE_STUDY_GUIDE: ("report", "study_guide.md", "course_study_guide.md"),
    # Slide decks download as PDF (or PPTX per course options), data tables as CSV. Refs: ISSUE-012
    ArtifactType.SLIDE_DECK: ("slide_deck", "slide_deck.pdf", "course_slide_deck.pdf"),
    ArtifactType.COURSE_SLIDE_DECK: ("slide_deck", "slide_deck.pdf", "course_slide_deck.pdf"),
    ArtifactType.INFOGRAPHIC: ("infographic", "infographic.png", "course_infographic.png"),
    ArtifactType.COURSE_INFOGRAPHIC: ("infographic", "infographic.png", "course_infographic.png"),
    ArtifactType.DATA_TABLE: ("data_table", "data_table.csv", "course_data_table.csv"),
    ArtifactType.COURSE_DATA_TABLE: ("data_table", "data_table.csv", "course_data_table.csv"),
    ArtifactType.VIDEO: ("video", "video.mp4", "course_video.mp4"),
    ArtifactType.COURSE_VIDEO: ("video", "video.mp4", "course_video.mp4"),
}

MIND_MAP_TYPES = (ArtifactType.MIND_MAP, ArtifactType.COURSE_MIND_MAP)

# A processed job: primary output path plus the NotebookLM artifact ids it produced.
ProcessResult = tuple[str, list[str]]


class ArtifactRunner:
    """Dispatches individual artifact generation, conversion, and NotebookLM in-app renaming.

    Downloads and renames always target the artifact id returned by the generate call, never
    "the latest artifact", so parallel workers cannot mix up lectures. Refs: ADR-004
    """

    def __init__(self, notebooklm_client: NotebookLMClientProtocol, config: AppConfig | None = None) -> None:
        """Initialize the artifact runner.

        Args:
            notebooklm_client: Client protocol for NotebookLM interactions.
            config: Application configuration settings.
        """
        self.notebooklm_client = notebooklm_client
        self.config = config or load_config()

    async def rename_after_generation(
        self, job: ArtifactJob, course: Course, nb_id: str, artifact_ids: list[str]
    ) -> None:
        """Rename the artifacts this job produced on NotebookLM using a standardized English title.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            artifact_ids: Artifact ids returned by the generate calls of this job.
        """
        lec = next((item for item in course.lectures if item.no == job.lecture_no), None)
        prefix = (
            get_lecture_prefix(lec.filename, lec.no)
            if (job.lecture_no is not None and lec)
            else get_course_range_prefix(course.lectures)
        )
        title = versioned_title(get_artifact_english_title(job.artifact_type, prefix), job.version)
        # Mind maps are notes, renamed through a different API. Refs: ISSUE-011
        rename = (
            self.notebooklm_client.rename_mind_map
            if job.artifact_type in MIND_MAP_TYPES
            else self.notebooklm_client.rename_artifact
        )
        for artifact_id in artifact_ids:
            try:
                await rename(nb_id, artifact_id, title)
                logger.info("Renamed artifact %s to '%s'", artifact_id, title)
            except Exception as err:
                logger.warning("Could not rename artifact %s on NotebookLM: %s", artifact_id, err)

    async def process_job(
        self,
        job: ArtifactJob,
        course: Course,
        nb_id: str,
        source_ids: list[str],
        out_dir: Path,
    ) -> str:
        """Dispatch generation and local format conversion for an artifact job.

        Args:
            job: The artifact job to execute.
            course: The associated Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers for context.
            out_dir: Filesystem output directory.

        Returns:
            Path string of the primary deliverable output file.
        """
        path, _ = await self.process_job_with_ids(job, course, nb_id, source_ids, out_dir)
        return path

    async def process_job_with_ids(
        self,
        job: ArtifactJob,
        course: Course,
        nb_id: str,
        source_ids: list[str],
        out_dir: Path,
    ) -> ProcessResult:
        """Run a job like `process_job` and also return the NotebookLM ids it produced.

        Args:
            job: The artifact job to execute.
            course: The associated Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers for context.
            out_dir: Filesystem output directory.

        Returns:
            Primary output path and the artifact / note ids (recorded on the job, ADR-005).
        """
        art_type = job.artifact_type
        result: ProcessResult
        if art_type in (ArtifactType.AUDIO, ArtifactType.COURSE_AUDIO):
            result = await self._process_audio(job, course, nb_id, source_ids, out_dir)
        elif art_type in QUIZ_TYPES:
            result = await self._process_quiz(job, course, nb_id, source_ids, out_dir)
        elif art_type == ArtifactType.FLASHCARDS:
            result = await self._process_flashcards(job, course, nb_id, source_ids, out_dir)
        elif art_type in (ArtifactType.MIND_MAP, ArtifactType.COURSE_MIND_MAP):
            result = await self._process_mindmap(job, course, nb_id, source_ids, out_dir)
        elif art_type in MOCK_EXAM_TYPES:
            result = await self._process_mock_exam(job, course, nb_id, source_ids, out_dir)
        elif art_type in REPORT_FORMATS:
            result = await self._process_report(job, course, nb_id, source_ids, out_dir)
        elif art_type in SIMPLE_OUTPUTS:
            result = await self._process_simple(job, course, nb_id, source_ids, out_dir)
        else:
            raise ValueError(f"Unsupported artifact type: {art_type}")

        path, artifact_ids = result
        await self.rename_after_generation(job, course, nb_id, artifact_ids)
        return path, artifact_ids

    async def _process_audio(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> ProcessResult:
        """Generate and save a Deep Dive audio overview in the course language.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: List of source identifiers to include.
            out_dir: Target output directory for files.

        Returns:
            Saved audio path and the generated artifact id.
        """
        art_id = await self.notebooklm_client.generate_audio(
            nb_id,
            source_ids,
            prompt=job.custom_prompt,
            language=course.language,
            options=course.generation_options,
        )
        # NotebookLM delivers MP4/AAC audio, so the file is .m4a. Refs: ISSUE-007
        if job.lecture_no is None:
            name = f"{job.course_code}_course_audio.m4a"
        else:
            name = f"{job.course_code}_L{job.lecture_no:02d}_audio.m4a"
        audio_file = out_dir / versioned_name(name, job.version)
        await self.notebooklm_client.download_audio(nb_id, str(audio_file), artifact_id=art_id)
        return str(audio_file), [art_id]

    async def _generate_quiz_batch(
        self,
        nb_id: str,
        source_ids: list[str],
        prompt: str,
        difficulty: str | None,
        tmp_json: Path,
        options: GenerationOptions | None = None,
    ) -> tuple[str, dict[str, object] | None]:
        """Generate one quiz batch and download exactly that artifact.

        Args:
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Quiz instructions.
            difficulty: 'easy', 'medium', 'hard', or None.
            tmp_json: Temporary download path.
            options: Course generation options (question quantity).

        Returns:
            Generated artifact id and the raw quiz JSON (None if nothing was downloaded).
        """
        art_id = await self.notebooklm_client.generate_quiz(
            nb_id, source_ids, prompt=prompt, difficulty=difficulty, options=options
        )
        await self.notebooklm_client.download_quiz(nb_id, str(tmp_json), artifact_id=art_id)
        raw = json.loads(tmp_json.read_text(encoding="utf-8")) if tmp_json.exists() else None
        return art_id, raw

    async def _process_quiz(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> ProcessResult:
        """Generate a 30-question quiz at the variant's difficulty, with dedup, markdown, and PDF.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers for the lecture.
            out_dir: Target output directory.

        Returns:
            Path to the resulting quiz.json and the generated artifact ids.

        Raises:
            NeedsReviewError: When fewer than 30 questions were collected; the partial quiz
                is saved under `needs_review/` and its path is carried on the error.
        """
        variant, difficulty = QUIZ_VARIANTS.get(job.artifact_type, ("1-基礎", None))
        variant_prefix = job.artifact_type.value
        prompt = (
            job.custom_prompt or f"Generate rigorous questions for {variant} in language: {course.language}"
        )
        batches: list[Quiz] = []
        art_ids: list[str] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            for attempt in range(3):
                tmp_json = Path(tmp_dir) / f"quiz_attempt_{attempt}.json"
                art_id, raw = await self._generate_quiz_batch(
                    nb_id, source_ids, prompt, difficulty, tmp_json, course.generation_options
                )
                art_ids.append(art_id)
                if raw is not None:
                    batches.append(
                        parse_notebooklm_quiz(
                            raw_data=raw,
                            course_code=course.code,
                            lecture_no=job.lecture_no or 0,
                            variant=variant,
                            source_pdf=f"{job.lecture_no:02d}.pdf",
                        )
                    )
                if merge_and_deduplicate_quizzes(batches, target_count=30)[1]:
                    break

        merged_quiz, is_complete = merge_and_deduplicate_quizzes(batches, target_count=30)
        if not is_complete:
            await self._quarantine_quiz(job, course, nb_id, art_ids, merged_quiz, target=30)

        return _save_quiz_files(
            out_dir, merged_quiz, file_prefix=versioned_name(variant_prefix, job.version)
        ), art_ids

    async def _quarantine_quiz(
        self, job: ArtifactJob, course: Course, nb_id: str, art_ids: list[str], quiz: Quiz, target: int
    ) -> None:
        """Rename the attempts, save an incomplete quiz under `needs_review/`, and raise.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            art_ids: Artifact ids of every generation attempt.
            quiz: Merged, incomplete quiz.
            target: Number of questions that was required.

        Raises:
            NeedsReviewError: Always; carries the quarantined JSON path.
        """
        prefix = versioned_name(job.artifact_type.value, job.version)
        scope = "course" if job.lecture_no is None else f"L{job.lecture_no}"
        await self.rename_after_generation(job, course, nb_id, art_ids)
        review_dir = self.config.needs_review_dir / f"{course.code}_{scope}_{prefix}"
        review_dir.mkdir(parents=True, exist_ok=True)
        incomplete_json = review_dir / f"{prefix}_quiz.json"
        incomplete_json.write_text(quiz_to_json(quiz), encoding="utf-8")
        count = len(quiz.questions)
        logger.warning("Quiz incomplete (%d/%d questions), quarantined to %s", count, target, review_dir)
        raise NeedsReviewError(f"Quiz has {count}/{target} questions", output_file=str(incomplete_json))

    async def _process_flashcards(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> ProcessResult:
        """Generate flashcards and save JSON and Anki CSV.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers.
            out_dir: Target output directory.

        Returns:
            Path of saved anki.csv and the generated artifact id.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_json = Path(tmp_dir) / "flashcards.json"
            art_id = await self.notebooklm_client.generate_flashcards(
                nb_id, source_ids, prompt=job.custom_prompt, options=course.generation_options
            )
            await self.notebooklm_client.download_flashcards(nb_id, str(tmp_json), artifact_id=art_id)
            raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))

        cards = parse_notebooklm_flashcards(raw_data)
        fc_json = out_dir / versioned_name("flashcards.json", job.version)
        anki_csv = out_dir / versioned_name("anki.csv", job.version)

        title = f"[{course.code}] L{job.lecture_no}"
        fc_json.write_text(flashcards_to_json(cards, title=title), encoding="utf-8")
        anki_tags = [course.code, f"L{job.lecture_no:02d}"]
        anki_csv.write_text(to_anki_csv(cards, tags=anki_tags), encoding="utf-8")
        return str(anki_csv), [art_id]

    async def _process_mindmap(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> ProcessResult:
        """Generate a mind map and export to JSON, OPML 2.0 XML, and Markdown.

        Mind maps are saved as NotebookLM notes; their note id is returned so the runner renames
        them through the mind map API (ISSUE-011).

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers.
            out_dir: Target output directory.

        Returns:
            Path of saved mindmap.opml and the mind map note id.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_json = Path(tmp_dir) / "mindmap.json"
            note_id = await self.notebooklm_client.generate_mind_map(
                nb_id, source_ids, prompt=job.custom_prompt, language=course.language
            )
            await self.notebooklm_client.download_mind_map(nb_id, str(tmp_json), artifact_id=note_id)
            raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))

        root = parse_notebooklm_mindmap(raw_data)
        mm_json = out_dir / versioned_name("mindmap.json", job.version)
        mm_opml = out_dir / versioned_name("mindmap.opml", job.version)
        mm_md = out_dir / versioned_name("mindmap.md", job.version)

        mm_json.write_text(mindmap_to_json(root), encoding="utf-8")
        mm_opml.write_text(to_opml(root), encoding="utf-8")
        mm_md.write_text(mindmap_to_markdown(root), encoding="utf-8")
        return str(mm_opml), [note_id]

    async def _process_mock_exam(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> ProcessResult:
        """Generate course-wide mock exam across all lecture sources.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: All source identifiers belonging to the course.
            out_dir: Target output directory.

        Returns:
            Path to resulting quiz.json and the generated artifact ids.

        Raises:
            NeedsReviewError: When fewer than the target questions were collected.
        """
        target_q = course.mock_exam_questions or 50
        batches: list[Quiz] = []
        art_ids: list[str] = []
        variant_prefix = job.artifact_type.value
        variant_title = (
            f"[{course.code}] 全課程學術精研期末考"
            if job.artifact_type == ArtifactType.COURSE_QUIZ_ACADEMIC
            else f"[{course.code}] 全課程核心觀念刷題考"
            if job.artifact_type == ArtifactType.COURSE_QUIZ_CONCEPT
            else f"[{course.code}] 全課程期末模擬考"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            for attempt in range(5):
                tmp_json = Path(tmp_dir) / f"mock_attempt_{attempt}.json"
                default_prompt = (
                    f"Comprehensive final exam batch {attempt + 1}, "
                    f"target={target_q}, language={course.language}"
                )
                prompt = job.custom_prompt or default_prompt
                art_id, raw = await self._generate_quiz_batch(
                    nb_id, source_ids, prompt, None, tmp_json, course.generation_options
                )
                art_ids.append(art_id)
                if raw is not None:
                    batches.append(
                        parse_notebooklm_quiz(
                            raw_data=raw,
                            course_code=course.code,
                            lecture_no=0,
                            variant="模擬考",
                            title=variant_title,
                        )
                    )
                if merge_and_deduplicate_quizzes(batches, target_count=target_q)[1]:
                    break

        final_quiz, is_complete = merge_and_deduplicate_quizzes(batches, target_count=target_q)
        if not is_complete:  # Refs: ISSUE-009
            await self._quarantine_quiz(job, course, nb_id, art_ids, final_quiz, target=target_q)
        return _save_quiz_files(
            out_dir, final_quiz, file_prefix=versioned_name(variant_prefix, job.version)
        ), art_ids

    async def _generate_simple(
        self, art_type: ArtifactType, course: Course, nb_id: str, source_ids: list[str], prompt: str | None
    ) -> str:
        """Call the generate method matching a single-shot artifact type.

        Args:
            art_type: Artifact type (study guide, slide deck, infographic, data table, video).
            course: Associated domain Course entity (for language).
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional tailored prompt.

        Returns:
            Generated artifact id.
        """
        client = self.notebooklm_client
        lang = course.language
        opts = course.generation_options
        if art_type in (ArtifactType.STUDY_GUIDE, ArtifactType.COURSE_STUDY_GUIDE):
            return await client.generate_report(
                nb_id, source_ids, prompt=prompt, language=lang, report_format="study_guide"
            )
        if art_type in (ArtifactType.SLIDE_DECK, ArtifactType.COURSE_SLIDE_DECK):
            return await client.generate_slide_deck(
                nb_id, source_ids, prompt=prompt, language=lang, options=opts
            )
        if art_type in (ArtifactType.INFOGRAPHIC, ArtifactType.COURSE_INFOGRAPHIC):
            return await client.generate_infographic(
                nb_id, source_ids, prompt=prompt, language=lang, options=opts
            )
        if art_type in (ArtifactType.DATA_TABLE, ArtifactType.COURSE_DATA_TABLE):
            return await client.generate_data_table(nb_id, source_ids, prompt=prompt, language=lang)
        return await client.generate_video(nb_id, source_ids, prompt=prompt, language=lang, options=opts)

    async def _process_simple(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> ProcessResult:
        """Generate a single-shot artifact and download exactly that artifact.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers.
            out_dir: Target output directory.

        Returns:
            Saved file path and the generated artifact id.
        """
        kind, lecture_name, course_name = SIMPLE_OUTPUTS[job.artifact_type]
        art_id = await self._generate_simple(job.artifact_type, course, nb_id, source_ids, job.custom_prompt)
        name = course_name if job.lecture_no is None else lecture_name
        opts = course.generation_options
        if kind == "slide_deck" and opts.slide_download == "pptx":
            name = name.removesuffix(".pdf") + ".pptx"
        out_file = out_dir / versioned_name(name, job.version)
        if kind == "slide_deck":
            await self.notebooklm_client.download_slide_deck(
                nb_id, str(out_file), artifact_id=art_id, output_format=opts.slide_download
            )
        else:
            downloader = getattr(self.notebooklm_client, f"download_{kind}")
            await downloader(nb_id, str(out_file), artifact_id=art_id)
        if kind == "infographic" and opts.device_exports and out_file.exists():
            try:
                export_device_versions(out_file)
            except Exception as err:  # device copies are a convenience; never fail the job
                logger.warning("Could not export device versions of %s: %s", out_file.name, err)
        return str(out_file), [art_id]

    async def _process_report(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> ProcessResult:
        """Generate and save a report artifact (Briefing Doc, Study Guide, Blog Post).

        Args:
            job: The artifact job.
            course: Course domain object.
            nb_id: Notebook identifier.
            source_ids: Sources to generate from.
            out_dir: Target folder.

        Returns:
            Output file path and the generated artifact id.
        """
        fmt = REPORT_FORMATS[job.artifact_type]
        is_course = job.lecture_no is None
        base_prefix = f"{course.code}_Course_{fmt}" if is_course else f"{course.code}_L{job.lecture_no}_{fmt}"
        out_prefix = versioned_name(base_prefix, job.version)
        art_id = await self.notebooklm_client.generate_report(
            notebook_id=nb_id,
            source_ids=source_ids,
            report_format=fmt,
            prompt=job.custom_prompt,
            language=course.language,
        )
        out_path = out_dir / f"{out_prefix}.md"
        await self.notebooklm_client.download_report(nb_id, str(out_path), artifact_id=art_id)

        html_path = out_dir / f"{out_prefix}_interactive.html"
        content_md = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
        html_wrapper = (
            '<!DOCTYPE html><html lang="zh-TW"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{out_prefix} — 互動研究報告</title>"
            "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;"
            "background:#0f172a;color:#f8fafc;padding:32px;line-height:1.7;max-width:850px;margin:0 auto;}"
            "pre{background:#1e293b;padding:16px;border-radius:8px;overflow-x:auto;white-space:pre-wrap;}"
            "</style></head><body>"
            f"<h1>{out_prefix}</h1><pre>{content_md}</pre></body></html>"
        )
        html_path.write_text(html_wrapper, encoding="utf-8")
        return str(out_path), [art_id]

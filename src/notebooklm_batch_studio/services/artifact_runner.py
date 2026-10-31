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
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Course,
    Quiz,
    get_artifact_english_title,
    get_course_range_prefix,
    get_lecture_prefix,
)
from notebooklm_batch_studio.domain.repositories import NotebookLMClientProtocol
from notebooklm_batch_studio.services.converters.flashcard_converter import (
    parse_notebooklm_flashcards,
    to_anki_csv,
)
from notebooklm_batch_studio.services.converters.flashcard_converter import (
    to_json as flashcards_to_json,
)
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


def _save_quiz_files(out_dir: Path, quiz: Quiz) -> str:
    """Save quiz markdown, JSON, interactive HTML, and PDF files to target directory.

    Args:
        out_dir: Destination folder.
        quiz: Domain Quiz entity.

    Returns:
        Path string of quiz.json.
    """
    exam_md = out_dir / "題目卷.md"
    ans_md = out_dir / "答案卷.md"
    final_json = out_dir / "quiz.json"
    interactive_html = out_dir / "interactive_quiz.html"
    exam_pdf = out_dir / "題目卷.pdf"
    ans_pdf = out_dir / "答案卷.pdf"

    exam_md.write_text(to_exam_markdown(quiz), encoding="utf-8")
    ans_md.write_text(to_answer_markdown(quiz), encoding="utf-8")
    final_json.write_text(quiz_to_json(quiz), encoding="utf-8")
    interactive_html.write_text(to_interactive_html(quiz), encoding="utf-8")
    to_pdf(quiz, exam_pdf, is_answer_key=False)
    to_pdf(quiz, ans_pdf, is_answer_key=True)

    return str(final_json)


class ArtifactRunner:
    """Dispatches individual artifact generation, conversion, and NotebookLM in-app renaming."""

    def __init__(self, notebooklm_client: NotebookLMClientProtocol, config: AppConfig | None = None) -> None:
        """Initialize the artifact runner.

        Args:
            notebooklm_client: Client protocol for NotebookLM interactions.
            config: Application configuration settings.
        """
        self.notebooklm_client = notebooklm_client
        self.config = config or load_config()

    async def rename_after_generation(self, job: ArtifactJob, course: Course, nb_id: str) -> None:
        """Rename the newly produced artifact on NotebookLM using standardized English title.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
        """
        lec = next((item for item in course.lectures if item.no == job.lecture_no), None)
        prefix = (
            get_lecture_prefix(lec.filename, lec.no)
            if (job.lecture_no is not None and lec)
            else get_course_range_prefix(course.lectures)
        )
        title = get_artifact_english_title(job.artifact_type, prefix)
        try:
            artifact_id = await self.notebooklm_client.find_latest_artifact(nb_id, job.artifact_type.value)
            if artifact_id:
                await self.notebooklm_client.rename_artifact(nb_id, artifact_id, title)
                logger.info("Successfully renamed artifact %s to '%s'", artifact_id, title)
        except Exception as err:
            logger.warning("Could not rename artifact on NotebookLM: %s", err)

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
        is_course = job.lecture_no is None
        art_type = job.artifact_type

        res: str
        if art_type in (ArtifactType.AUDIO, ArtifactType.COURSE_AUDIO):
            res = await self._process_audio(job, nb_id, source_ids, out_dir, is_course)
        elif art_type in (
            ArtifactType.QUIZ_1,
            ArtifactType.QUIZ_2,
            ArtifactType.QUIZ_3,
            ArtifactType.QUIZ_ACADEMIC,
            ArtifactType.QUIZ_CONCEPT,
        ):
            res = await self._process_quiz(job, course, nb_id, source_ids, out_dir)
        elif art_type == ArtifactType.FLASHCARDS:
            res = await self._process_flashcards(job, course, nb_id, source_ids, out_dir)
        elif art_type in (ArtifactType.MIND_MAP, ArtifactType.COURSE_MIND_MAP):
            res = await self._process_mindmap(job, nb_id, source_ids, out_dir)
        elif art_type in (
            ArtifactType.COURSE_MOCK_EXAM,
            ArtifactType.COURSE_QUIZ_ACADEMIC,
            ArtifactType.COURSE_QUIZ_CONCEPT,
        ):
            res = await self._process_mock_exam(job, course, nb_id, source_ids, out_dir)
        elif art_type in (ArtifactType.STUDY_GUIDE, ArtifactType.COURSE_STUDY_GUIDE):
            res = await self._process_study_guide(
                course, nb_id, source_ids, out_dir, is_course, job.custom_prompt
            )
        elif art_type in (
            ArtifactType.REPORTS_BRIEFING,
            ArtifactType.REPORTS_STUDY_GUIDE,
            ArtifactType.REPORTS_BLOG_POST,
            ArtifactType.COURSE_REPORTS_BRIEFING,
            ArtifactType.COURSE_REPORTS_STUDY_GUIDE,
            ArtifactType.COURSE_REPORTS_BLOG_POST,
        ):
            res = await self._process_report(job, course, nb_id, source_ids, out_dir, is_course)
        elif art_type in (ArtifactType.SLIDE_DECK, ArtifactType.COURSE_SLIDE_DECK):
            res = await self._process_slide_deck(
                course, nb_id, source_ids, out_dir, is_course, job.custom_prompt
            )
        elif art_type in (ArtifactType.INFOGRAPHIC, ArtifactType.COURSE_INFOGRAPHIC):
            res = await self._process_infographic(
                course, nb_id, source_ids, out_dir, is_course, job.custom_prompt
            )
        elif art_type in (ArtifactType.DATA_TABLE, ArtifactType.COURSE_DATA_TABLE):
            res = await self._process_data_table(
                course, nb_id, source_ids, out_dir, is_course, job.custom_prompt
            )
        elif art_type in (ArtifactType.VIDEO, ArtifactType.COURSE_VIDEO):
            res = await self._process_video(course, nb_id, source_ids, out_dir, is_course, job.custom_prompt)
        else:
            raise ValueError(f"Unsupported artifact type: {art_type}")

        await self.rename_after_generation(job, course, nb_id)
        return res

    async def _process_audio(
        self,
        job: ArtifactJob,
        nb_id: str,
        source_ids: list[str],
        out_dir: Path,
        is_course_wide: bool = False,
    ) -> str:
        """Generate and save Deep Dive Audio MP3.

        Args:
            job: Current artifact job.
            nb_id: NotebookLM notebook identifier.
            source_ids: List of source identifiers to include.
            out_dir: Target output directory for files.
            is_course_wide: Whether generating course-wide audio.

        Returns:
            Path string of the saved audio file.
        """
        await self.notebooklm_client.generate_audio(nb_id, source_ids)
        if is_course_wide or job.lecture_no is None:
            audio_file = out_dir / f"{job.course_code}_course_audio.mp3"
        else:
            audio_file = out_dir / f"{job.course_code}_L{job.lecture_no:02d}_audio.mp3"
        await self.notebooklm_client.download_audio(nb_id, str(audio_file))
        return str(audio_file)

    async def _process_quiz(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> str:
        """Generate 30-question quiz with deduplication, markdown, and PDF output.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers for the lecture.
            out_dir: Target output directory.

        Returns:
            Path string to the resulting quiz.json or quarantined file.
        """
        variant_map = {
            ArtifactType.QUIZ_1: "1-基礎",
            ArtifactType.QUIZ_2: "2-理解",
            ArtifactType.QUIZ_3: "3-模擬考",
            ArtifactType.QUIZ_ACADEMIC: "學術精研",
            ArtifactType.QUIZ_CONCEPT: "概念刷題",
        }
        variant = variant_map.get(job.artifact_type, "1-基礎")
        batches: list[Quiz] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            for attempt in range(3):
                tmp_json = Path(tmp_dir) / f"quiz_attempt_{attempt}.json"
                prompt = f"Generate rigorous questions for {variant} in language: {course.language}"
                await self.notebooklm_client.generate_quiz(nb_id, source_ids, prompt=prompt)
                await self.notebooklm_client.download_quiz(nb_id, str(tmp_json))

                if tmp_json.exists():
                    raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))
                    parsed = parse_notebooklm_quiz(
                        raw_data=raw_data,
                        course_code=course.code,
                        lecture_no=job.lecture_no or 0,
                        variant=variant,
                        source_pdf=f"{job.lecture_no:02d}.pdf",
                    )
                    batches.append(parsed)

                merged, is_complete = merge_and_deduplicate_quizzes(batches, target_count=30)
                if is_complete:
                    break

        merged_quiz, is_complete = merge_and_deduplicate_quizzes(batches, target_count=30)
        if not is_complete:
            review_dir = self.config.needs_review_dir / f"{course.code}_L{job.lecture_no}_{variant}"
            review_dir.mkdir(parents=True, exist_ok=True)
            incomplete_json = review_dir / "quiz.json"
            incomplete_json.write_text(quiz_to_json(merged_quiz), encoding="utf-8")
            logger.warning(
                "Quiz incomplete (%d questions), quarantined to %s",
                len(merged_quiz.questions),
                review_dir,
            )
            return str(incomplete_json)

        return _save_quiz_files(out_dir, merged_quiz)

    async def _process_flashcards(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> str:
        """Generate flashcards and save JSON and Anki CSV.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers.
            out_dir: Target output directory.

        Returns:
            Path string of saved anki.csv.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_json = Path(tmp_dir) / "flashcards.json"
            await self.notebooklm_client.generate_flashcards(nb_id, source_ids)
            await self.notebooklm_client.download_flashcards(nb_id, str(tmp_json))
            raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))

        cards = parse_notebooklm_flashcards(raw_data)
        fc_json = out_dir / "flashcards.json"
        anki_csv = out_dir / "anki.csv"

        title = f"[{course.code}] L{job.lecture_no}"
        fc_json.write_text(flashcards_to_json(cards, title=title), encoding="utf-8")
        anki_tags = [course.code, f"L{job.lecture_no:02d}"]
        anki_csv.write_text(to_anki_csv(cards, tags=anki_tags), encoding="utf-8")
        return str(anki_csv)

    async def _process_mindmap(
        self, job: ArtifactJob, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> str:
        """Generate mind map and export to JSON, OPML 2.0 XML, and Markdown.

        Args:
            job: Current artifact job.
            nb_id: NotebookLM notebook identifier.
            source_ids: Selected source identifiers.
            out_dir: Target output directory.

        Returns:
            Path string of saved mindmap.opml.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_json = Path(tmp_dir) / "mindmap.json"
            await self.notebooklm_client.generate_mind_map(nb_id, source_ids)
            await self.notebooklm_client.download_mind_map(nb_id, str(tmp_json))
            raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))

        root = parse_notebooklm_mindmap(raw_data)
        mm_json = out_dir / "mindmap.json"
        mm_opml = out_dir / "mindmap.opml"
        mm_md = out_dir / "mindmap.md"

        mm_json.write_text(mindmap_to_json(root), encoding="utf-8")
        mm_opml.write_text(to_opml(root), encoding="utf-8")
        mm_md.write_text(mindmap_to_markdown(root), encoding="utf-8")
        return str(mm_opml)

    async def _process_mock_exam(
        self, job: ArtifactJob, course: Course, nb_id: str, source_ids: list[str], out_dir: Path
    ) -> str:
        """Generate course-wide mock exam across all lecture sources.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: All source identifiers belonging to the course.
            out_dir: Target output directory.

        Returns:
            Path string to resulting quiz.json.
        """
        target_q = course.mock_exam_questions or 50
        batches: list[Quiz] = []
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
                prompt = (
                    f"Comprehensive final exam batch {attempt + 1}, target={target_q}, "
                    f"language={course.language}"
                )
                await self.notebooklm_client.generate_quiz(nb_id, source_ids, prompt=prompt)
                await self.notebooklm_client.download_quiz(nb_id, str(tmp_json))
                if tmp_json.exists():
                    raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))
                    batches.append(
                        parse_notebooklm_quiz(
                            raw_data=raw_data,
                            course_code=course.code,
                            lecture_no=0,
                            variant="模擬考",
                            title=variant_title,
                        )
                    )
                merged, is_complete = merge_and_deduplicate_quizzes(batches, target_count=target_q)
                if is_complete:
                    break

        final_quiz, _ = merge_and_deduplicate_quizzes(batches, target_count=target_q)
        return _save_quiz_files(out_dir, final_quiz)

    async def _process_study_guide(
        self,
        course: Course,
        nb_id: str,
        source_ids: list[str],
        out_dir: Path,
        is_course_wide: bool = False,
        prompt: str | None = None,
    ) -> str:
        """Generate and save Study Guide Markdown.

        Args:
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: List of source identifiers to include.
            out_dir: Target output directory for files.
            is_course_wide: Whether generating course-wide or lecture study guide.
            prompt: Optional tailored prompt.

        Returns:
            Path string of saved report file.
        """
        await self.notebooklm_client.generate_report(
            nb_id, source_ids, prompt=prompt, language=course.language
        )
        filename = "course_study_guide.md" if is_course_wide else "study_guide.md"
        guide_file = out_dir / filename
        await self.notebooklm_client.download_report(nb_id, str(guide_file))
        return str(guide_file)

    async def _process_slide_deck(
        self,
        course: Course,
        nb_id: str,
        source_ids: list[str],
        out_dir: Path,
        is_course_wide: bool = False,
        prompt: str | None = None,
    ) -> str:
        """Generate and save presentation slide deck outline.

        Args:
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: List of source identifiers to include.
            out_dir: Target output directory for files.
            is_course_wide: Whether generating course-wide or lecture slide deck.
            prompt: Optional tailored prompt.

        Returns:
            Path string of saved slide deck file.
        """
        await self.notebooklm_client.generate_slide_deck(
            nb_id, source_ids, prompt=prompt, language=course.language
        )
        filename = "course_slide_deck.md" if is_course_wide else "slide_deck.md"
        deck_file = out_dir / filename
        await self.notebooklm_client.download_slide_deck(nb_id, str(deck_file))
        return str(deck_file)

    async def _process_infographic(
        self,
        course: Course,
        nb_id: str,
        source_ids: list[str],
        out_dir: Path,
        is_course_wide: bool = False,
        prompt: str | None = None,
    ) -> str:
        """Generate and save visual infographic.

        Args:
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: List of source identifiers to include.
            out_dir: Target output directory for files.
            is_course_wide: Whether generating course-wide or lecture infographic.
            prompt: Optional tailored prompt.

        Returns:
            Path string of saved image file.
        """
        await self.notebooklm_client.generate_infographic(
            nb_id, source_ids, prompt=prompt, language=course.language
        )
        filename = "course_infographic.png" if is_course_wide else "infographic.png"
        img_file = out_dir / filename
        await self.notebooklm_client.download_infographic(nb_id, str(img_file))
        return str(img_file)

    async def _process_data_table(
        self,
        course: Course,
        nb_id: str,
        source_ids: list[str],
        out_dir: Path,
        is_course_wide: bool = False,
        prompt: str | None = None,
    ) -> str:
        """Generate and save comparison data table.

        Args:
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: List of source identifiers to include.
            out_dir: Target output directory for files.
            is_course_wide: Whether generating course-wide or lecture table.
            prompt: Optional tailored prompt.

        Returns:
            Path string of saved markdown table file.
        """
        await self.notebooklm_client.generate_data_table(
            nb_id, source_ids, prompt=prompt, language=course.language
        )
        filename = "course_data_table.md" if is_course_wide else "data_table.md"
        table_file = out_dir / filename
        await self.notebooklm_client.download_data_table(nb_id, str(table_file))
        return str(table_file)

    async def _process_video(
        self,
        course: Course,
        nb_id: str,
        source_ids: list[str],
        out_dir: Path,
        is_course_wide: bool = False,
        prompt: str | None = None,
    ) -> str:
        """Generate and save video overview.

        Args:
            course: Associated domain Course entity.
            nb_id: NotebookLM notebook identifier.
            source_ids: List of source identifiers to include.
            out_dir: Target output directory for files.
            is_course_wide: Whether generating course-wide or lecture video.
            prompt: Optional tailored prompt.

        Returns:
            Path string of saved video file.
        """
        await self.notebooklm_client.generate_video(
            nb_id, source_ids, prompt=prompt, language=course.language
        )
        filename = "course_video.mp4" if is_course_wide else "video.mp4"
        vid_file = out_dir / filename
        await self.notebooklm_client.download_video(nb_id, str(vid_file))
        return str(vid_file)

    async def _process_report(
        self,
        job: ArtifactJob,
        course: Course,
        nb_id: str,
        source_ids: list[str],
        out_dir: Path,
        is_course: bool,
    ) -> str:
        """Generate and save reports artifact (Briefing Doc, Study Guide, Blog Post).

        Args:
            job: The artifact job.
            course: Course domain object.
            nb_id: Notebook identifier.
            source_ids: Sources to generate from.
            out_dir: Target folder.
            is_course: Whether this is course-wide.

        Returns:
            Output file path.
        """
        art_type = job.artifact_type
        fmt = "briefing_doc"
        if art_type in (ArtifactType.REPORTS_STUDY_GUIDE, ArtifactType.COURSE_REPORTS_STUDY_GUIDE):
            fmt = "study_guide"
        elif art_type in (ArtifactType.REPORTS_BLOG_POST, ArtifactType.COURSE_REPORTS_BLOG_POST):
            fmt = "blog_post"

        out_prefix = (
            f"{course.code}_Course_{fmt}"
            if is_course
            else f"{course.code}_L{job.lecture_no}_{fmt}"
        )
        task_id = await self.notebooklm_client.generate_report(
            notebook_id=nb_id,
            source_ids=source_ids,
            report_format=fmt,
            prompt=job.custom_prompt,
            language=course.language,
        )
        await self.notebooklm_client.wait_for_completion(nb_id, task_id)
        out_path = out_dir / f"{out_prefix}.md"
        await self.notebooklm_client.download_report(nb_id, str(out_path))

        html_path = out_dir / f"{out_prefix}_interactive.html"
        content_md = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
        html_wrapper = (
            "<!DOCTYPE html><html lang=\"zh-TW\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{out_prefix} — 互動研究報告</title>"
            "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;"
            "background:#0f172a;color:#f8fafc;padding:32px;line-height:1.7;max-width:850px;margin:0 auto;}"
            "pre{background:#1e293b;padding:16px;border-radius:8px;overflow-x:auto;white-space:pre-wrap;}"
            "</style></head><body>"
            f"<h1>{out_prefix}</h1><pre>{content_md}</pre></body></html>"
        )
        html_path.write_text(html_wrapper, encoding="utf-8")
        return str(out_path)

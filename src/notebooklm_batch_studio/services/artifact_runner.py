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
from notebooklm_batch_studio.services.converters.report_converter import report_to_html
from notebooklm_batch_studio.services.quiz_runner import (
    MOCK_EXAM_TYPES as MOCK_EXAM_TYPES,
)
from notebooklm_batch_studio.services.quiz_runner import (
    QUIZ_TYPES as QUIZ_TYPES,
)
from notebooklm_batch_studio.services.quiz_runner import (
    QUIZ_VARIANTS as QUIZ_VARIANTS,
)
from notebooklm_batch_studio.services.quiz_runner import (
    JobTarget as JobTarget,
)
from notebooklm_batch_studio.services.quiz_runner import (
    ProcessResult as ProcessResult,
)
from notebooklm_batch_studio.services.quiz_runner import (
    QuizRunner,
)

logger = logging.getLogger(__name__)

REPORT_FORMATS = {
    ArtifactType.REPORTS_BRIEFING: "briefing_doc",
    ArtifactType.COURSE_REPORTS_BRIEFING: "briefing_doc",
    ArtifactType.REPORTS_STUDY_GUIDE: "study_guide",
    ArtifactType.COURSE_REPORTS_STUDY_GUIDE: "study_guide",
    ArtifactType.REPORTS_BLOG_POST: "blog_post",
    ArtifactType.COURSE_REPORTS_BLOG_POST: "blog_post",
    ArtifactType.REPORTS_CONCEPT: "concept_explanation",
    ArtifactType.COURSE_REPORTS_CONCEPT: "concept_explanation",
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


class ArtifactRunner:
    """Dispatches individual artifact generation, conversion, and Gemini Notebook in-app renaming.

    Downloads and renames always target the artifact id returned by the generate call, never
    "the latest artifact", so parallel workers cannot mix up lectures. Refs: ADR-004
    """

    def __init__(self, notebooklm_client: NotebookLMClientProtocol, config: AppConfig | None = None) -> None:
        """Initialize the artifact runner.

        Args:
            notebooklm_client: Client protocol for Gemini Notebook interactions.
            config: Application configuration settings.
        """
        self.notebooklm_client = notebooklm_client
        self.config = config or load_config()
        self.quiz_runner = QuizRunner(
            notebooklm_client, self.config.needs_review_dir, self.rename_after_generation
        )

    async def rename_after_generation(
        self, job: ArtifactJob, course: Course, nb_id: str, artifact_ids: list[str]
    ) -> None:
        """Rename the artifacts this job produced on Gemini Notebook using a standardized English title.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            nb_id: Gemini Notebook notebook identifier.
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
        total = len(artifact_ids)
        for index, artifact_id in enumerate(artifact_ids, start=1):
            # A quiz collected over several batches gets "(1/3)", "(2/3)"... so the batches of one
            # quiz are told apart on Gemini Notebook instead of showing identical titles.
            batch_title = f"{title} ({index}/{total})" if total > 1 else title
            try:
                await rename(nb_id, artifact_id, batch_title)
                logger.info("Renamed artifact %s to '%s'", artifact_id, batch_title)
            except Exception as err:
                logger.warning("Could not rename artifact %s on Gemini Notebook: %s", artifact_id, err)

    async def process_job(self, job: ArtifactJob, course: Course, target: JobTarget) -> str:
        """Dispatch generation and local format conversion for an artifact job.

        Args:
            job: The artifact job to execute.
            course: The associated Course entity.
            target: Resolved Gemini Notebook target and output directory.

        Returns:
            Path string of the primary deliverable output file.
        """
        path, _ = await self.process_job_with_ids(job, course, target)
        return path

    async def process_job_with_ids(
        self, job: ArtifactJob, course: Course, target: JobTarget
    ) -> ProcessResult:
        """Run a job like `process_job` and also return the Gemini Notebook ids it produced.

        Args:
            job: The artifact job to execute.
            course: The associated Course entity.
            target: Resolved Gemini Notebook target and output directory.

        Returns:
            Primary output path and the artifact / note ids (recorded on the job, ADR-005).
        """
        art_type = job.artifact_type
        if art_type in (ArtifactType.AUDIO, ArtifactType.COURSE_AUDIO):
            result = await self._process_audio(job, course, target)
        elif art_type in QUIZ_TYPES:
            result = await self.quiz_runner.process_quiz(job, course, target)
        elif art_type == ArtifactType.FLASHCARDS:
            result = await self._process_flashcards(job, course, target)
        elif art_type in MIND_MAP_TYPES:
            result = await self._process_mindmap(job, course, target)
        elif art_type in MOCK_EXAM_TYPES:
            result = await self.quiz_runner.process_mock_exam(job, course, target)
        elif art_type in REPORT_FORMATS:
            result = await self._process_report(job, course, target)
        elif art_type in SIMPLE_OUTPUTS:
            result = await self._process_simple(job, course, target)
        else:
            raise ValueError(f"Unsupported artifact type: {art_type}")

        path, artifact_ids = result
        await self.rename_after_generation(job, course, target.nb_id, artifact_ids)
        return path, artifact_ids

    async def _process_audio(self, job: ArtifactJob, course: Course, target: JobTarget) -> ProcessResult:
        """Generate and save a Deep Dive audio overview in the course language.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            target: Resolved Gemini Notebook target and output directory.

        Returns:
            Saved audio path and the generated artifact id.
        """
        art_id = await self.notebooklm_client.generate_audio(
            target.nb_id,
            target.source_ids,
            prompt=job.custom_prompt,
            language=course.language,
            options=course.generation_options,
        )
        # Gemini Notebook delivers MP4/AAC audio, so the file is .m4a. Refs: ISSUE-007
        name = (
            f"{job.course_code}_course_audio.m4a"
            if job.lecture_no is None
            else f"{job.course_code}_L{job.lecture_no:02d}_audio.m4a"
        )
        audio_file = target.out_dir / versioned_name(name, job.version)
        await self.notebooklm_client.download_audio(target.nb_id, str(audio_file), artifact_id=art_id)
        return str(audio_file), [art_id]

    async def _process_flashcards(self, job: ArtifactJob, course: Course, target: JobTarget) -> ProcessResult:
        """Generate flashcards and save JSON and Anki CSV.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            target: Resolved Gemini Notebook target and output directory.

        Returns:
            Path of saved anki.csv and the generated artifact id.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_json = Path(tmp_dir) / "flashcards.json"
            art_id = await self.notebooklm_client.generate_flashcards(
                target.nb_id,
                target.source_ids,
                prompt=job.custom_prompt,
                options=course.generation_options,
            )
            await self.notebooklm_client.download_flashcards(target.nb_id, str(tmp_json), artifact_id=art_id)
            raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))

        cards = parse_notebooklm_flashcards(raw_data)
        fc_json = target.out_dir / versioned_name("flashcards.json", job.version)
        anki_csv = target.out_dir / versioned_name("anki.csv", job.version)
        fc_json.write_text(
            flashcards_to_json(cards, title=f"[{course.code}] L{job.lecture_no}"), encoding="utf-8"
        )
        anki_csv.write_text(
            to_anki_csv(cards, tags=[course.code, f"L{job.lecture_no:02d}"]), encoding="utf-8"
        )
        return str(anki_csv), [art_id]

    async def _process_mindmap(self, job: ArtifactJob, course: Course, target: JobTarget) -> ProcessResult:
        """Generate a mind map and export to JSON, OPML 2.0 XML, and Markdown.

        Mind maps are saved as Gemini Notebook notes; their note id is returned so the runner renames
        them through the mind map API (ISSUE-011).

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            target: Resolved Gemini Notebook target and output directory.

        Returns:
            Path of saved mindmap.opml and the mind map note id.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_json = Path(tmp_dir) / "mindmap.json"
            note_id = await self.notebooklm_client.generate_mind_map(
                target.nb_id, target.source_ids, prompt=job.custom_prompt, language=course.language
            )
            await self.notebooklm_client.download_mind_map(target.nb_id, str(tmp_json), artifact_id=note_id)
            raw_data = json.loads(tmp_json.read_text(encoding="utf-8"))

        root = parse_notebooklm_mindmap(raw_data)
        target.out_dir.joinpath(versioned_name("mindmap.json", job.version)).write_text(
            mindmap_to_json(root), encoding="utf-8"
        )
        mm_opml = target.out_dir / versioned_name("mindmap.opml", job.version)
        mm_opml.write_text(to_opml(root), encoding="utf-8")
        target.out_dir.joinpath(versioned_name("mindmap.md", job.version)).write_text(
            mindmap_to_markdown(root), encoding="utf-8"
        )
        return str(mm_opml), [note_id]

    async def _generate_simple(self, job: ArtifactJob, course: Course, target: JobTarget) -> str:
        """Call the generate method matching a single-shot artifact type.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity (for language and options).
            target: Resolved Gemini Notebook target and source IDs.

        Returns:
            Generated artifact id.
        """
        client, art_type = self.notebooklm_client, job.artifact_type
        lang, opts, prompt = course.language, course.generation_options, job.custom_prompt
        if art_type in (ArtifactType.STUDY_GUIDE, ArtifactType.COURSE_STUDY_GUIDE):
            return await client.generate_report(
                target.nb_id, target.source_ids, prompt=prompt, language=lang, report_format="study_guide"
            )
        if art_type in (ArtifactType.SLIDE_DECK, ArtifactType.COURSE_SLIDE_DECK):
            return await client.generate_slide_deck(
                target.nb_id, target.source_ids, prompt=prompt, language=lang, options=opts
            )
        if art_type in (ArtifactType.INFOGRAPHIC, ArtifactType.COURSE_INFOGRAPHIC):
            return await client.generate_infographic(
                target.nb_id, target.source_ids, prompt=prompt, language=lang, options=opts
            )
        if art_type in (ArtifactType.DATA_TABLE, ArtifactType.COURSE_DATA_TABLE):
            return await client.generate_data_table(
                target.nb_id, target.source_ids, prompt=prompt, language=lang
            )
        return await client.generate_video(
            target.nb_id, target.source_ids, prompt=prompt, language=lang, options=opts
        )

    async def _process_simple(self, job: ArtifactJob, course: Course, target: JobTarget) -> ProcessResult:
        """Generate a single-shot artifact and download exactly that artifact.

        Args:
            job: Current artifact job.
            course: Associated domain Course entity.
            target: Resolved Gemini Notebook target and output directory.

        Returns:
            Saved file path and the generated artifact id.
        """
        kind, lecture_name, course_name = SIMPLE_OUTPUTS[job.artifact_type]
        art_id = await self._generate_simple(job, course, target)
        name = course_name if job.lecture_no is None else lecture_name
        opts = course.generation_options
        if kind == "slide_deck" and opts.slide_download == "pptx":
            name = name.removesuffix(".pdf") + ".pptx"
        out_file = target.out_dir / versioned_name(name, job.version)
        if kind == "slide_deck":
            await self.notebooklm_client.download_slide_deck(
                target.nb_id, str(out_file), artifact_id=art_id, output_format=opts.slide_download
            )
        else:
            downloader = getattr(self.notebooklm_client, f"download_{kind}")
            await downloader(target.nb_id, str(out_file), artifact_id=art_id)
        if kind == "infographic" and opts.device_exports and out_file.exists():
            try:
                export_device_versions(out_file)
            except Exception as err:  # device copies are a convenience; never fail the job
                logger.warning("Could not export device versions of %s: %s", out_file.name, err)
        return str(out_file), [art_id]

    async def _process_report(self, job: ArtifactJob, course: Course, target: JobTarget) -> ProcessResult:
        """Generate and save a report artifact (Briefing Doc, Study Guide, Blog Post).

        Args:
            job: The artifact job.
            course: Course domain object.
            target: Resolved Gemini Notebook target and output directory.

        Returns:
            Output file path and the generated artifact id.
        """
        fmt = REPORT_FORMATS[job.artifact_type]
        is_course = job.lecture_no is None
        base_prefix = f"{course.code}_Course_{fmt}" if is_course else f"{course.code}_L{job.lecture_no}_{fmt}"
        out_prefix = versioned_name(base_prefix, job.version)
        art_id = await self.notebooklm_client.generate_report(
            notebook_id=target.nb_id,
            source_ids=target.source_ids,
            report_format=fmt,
            prompt=job.custom_prompt,
            language=course.language,
        )
        out_path = target.out_dir / f"{out_prefix}.md"
        await self.notebooklm_client.download_report(target.nb_id, str(out_path), artifact_id=art_id)

        html_path = target.out_dir / f"{out_prefix}_interactive.html"
        content_md = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
        html_path.write_text(report_to_html(out_prefix, content_md), encoding="utf-8")
        return str(out_path), [art_id]

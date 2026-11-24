"""Phase 1 modular Markdown note generation service (Refs: ADR-012).

Orchestrates prompt loading from standalone `.md` templates, dual-backend
generation (`gemini_web` primary and `notebooklm` fallback) via injected
driver factories, step validation, version archiving, and chapter `.md` stitching.
"""

from __future__ import annotations

import logging
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generator

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.note_pipeline import (
    STANDARD_NOTE_STEPS,
    DriverUnavailableError,
    GenerationPausedError,
    NotePipelineStep,
    QuotaExceededError,
)
from notebooklm_batch_studio.domain.path_safety import validate_path_segment
from notebooklm_batch_studio.services.notes.chapter_normalizer import normalize_step_markdown
from notebooklm_batch_studio.services.notes.module_composer import compose_chapter_from_modules
from notebooklm_batch_studio.services.notes.module_prompts import (
    StepPromptContext,
    list_module_prompt_specs,
    load_module_prompt,
)
from notebooklm_batch_studio.services.notes.note_paths import ChapterNoteRequest, NotePathResolver
from notebooklm_batch_studio.services.notes.note_sync import (
    import_legacy_notes,
    list_chapter_notes,
    push_chapter_note_to_source,
)
from notebooklm_batch_studio.services.notes.state_manager import NoteStateManager
from notebooklm_batch_studio.services.notes.step_validator import validate_step_output

__all__ = ["ChapterNoteRequest", "NotePipelineService"]

logger = logging.getLogger(__name__)


def _select_steps(steps_override: list[str] | None) -> list[NotePipelineStep]:
    """Filter standard 7 steps when `steps_override` is provided.

    Args:
        steps_override: Optional list of step IDs such as `["03_qec"]`.

    Returns:
        Ordered list of `NotePipelineStep` items to execute.
    """
    if not steps_override:
        return list(STANDARD_NOTE_STEPS)
    wanted = set(steps_override)
    return [step for step in STANDARD_NOTE_STEPS if step.step_id in wanted]


def _archive_existing_file(path: Path, archive_dir: Path) -> None:
    """Copy an existing file into `archive_dir` before overwriting on rerun.

    Args:
        path: Existing file to preserve.
        archive_dir: Timestamped archive folder.
    """
    if not path.is_file():
        return
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, archive_dir / path.name)


class NotePipelineService:
    """Coordinates modular `.md` note generation, stitching, and prompt preview."""

    def __init__(
        self,
        config: AppConfig,
        driver_factory: Callable[[ChapterNoteRequest], Any] | None = None,
        study_dir_resolver: Callable[[str], Path | None] | None = None,
        source_dir_resolver: Callable[[str], Path | None] | None = None,
    ) -> None:
        """Initialize the note pipeline service.

        Args:
            config: Immutable application configuration.
            driver_factory: Factory returning a context manager yielding a driver.
            study_dir_resolver: Optional callback resolving `course_key -> study_dir`.
            source_dir_resolver: Optional callback resolving `course_key -> registered PDF folder`,
                the only place outside `DATA_DIR` / `STUDY_ROOT_DIR` a chapter PDF may come from.
        """
        self.config = config
        self._driver_factory = driver_factory
        self.paths = NotePathResolver(config, study_dir_resolver, source_dir_resolver)
        self.state = NoteStateManager(config.notes_state_dir)
        self.override_prompt_dir = config.prompt_override_dir

    def list_prompts(self) -> list[dict[str, str]]:
        """List all standalone modular prompt `.md` templates.

        Returns:
            List of template metadata dictionaries.
        """
        return list_module_prompt_specs(override_dir=self.override_prompt_dir)

    def preview_prompt(self, step_id: str, context: StepPromptContext) -> dict[str, str]:
        """Render one module's `.md` prompt with chapter metadata for preview/copy.

        Args:
            step_id: Step identifier such as `01_mindmap`.
            context: Course and chapter metadata.

        Returns:
            Dictionary with `step_id` and `prompt`.
        """
        prompt = load_module_prompt(step_id, context, override_dir=self.override_prompt_dir)
        return {"step_id": step_id, "prompt": prompt}

    def get_status(self, course_key: str) -> dict[str, Any]:
        """Return persisted note generation state and pause flag for a course.

        Args:
            course_key: Course identifier.

        Returns:
            Course state dictionary including `paused` boolean.
        """
        validate_path_segment(course_key, "course_key")
        data = self.state.load_course_state(course_key)
        data["paused"] = self.state.is_pause_requested(course_key)
        return data

    def request_pause(self, course_key: str) -> dict[str, Any]:
        """Request a clean pause after the current step finishes.

        Args:
            course_key: Course identifier.

        Returns:
            Updated status summary.
        """
        validate_path_segment(course_key, "course_key")
        self.state.request_pause(course_key)
        return {"course_key": course_key, "paused": True}

    def clear_pause(self, course_key: str) -> dict[str, Any]:
        """Clear any active pause request for a course.

        Args:
            course_key: Course identifier.

        Returns:
            Updated status summary.
        """
        validate_path_segment(course_key, "course_key")
        self.state.clear_pause(course_key)
        return {"course_key": course_key, "paused": False}

    @contextmanager
    def _acquire_driver(self, request: ChapterNoteRequest) -> Generator[Any, None, None]:
        """Acquire a generation driver from the configured driver factory.

        Args:
            request: Chapter note request specifying backend and target metadata.

        Yields:
            Active driver implementing `open_chapter_chat`, `send_prompt_and_read`, etc.
        """
        if self._driver_factory is None:
            raise DriverUnavailableError("尚未設定筆記生成驅動程式工廠（driver_factory）。")
        with self._driver_factory(request) as drv:
            yield drv

    def _run_single_step(
        self,
        driver: Any,
        step: NotePipelineStep,
        request: ChapterNoteRequest,
        module_dir: Path,
    ) -> Path:
        """Execute one prompt step, validate output, and write `<step_id>.md`.

        Args:
            driver: Active generation driver.
            step: Pipeline step definition.
            request: Chapter request metadata.
            module_dir: Output folder for module files.

        Returns:
            Path to the written module `.md` file.

        Raises:
            RuntimeError: When validation fails on a non-soft-fail step.
        """
        ctx = StepPromptContext(request.course_name, request.chapter_id, request.chapter_title)
        prompt = load_module_prompt(step.step_id, ctx, override_dir=self.override_prompt_dir)
        timeout = self.config.gemini_outline_timeout_seconds if step.step_id == "02_outline" else 360
        raw_reply = driver.send_prompt_and_read(
            prompt,
            expected_model=request.model,
            timeout_seconds=timeout,
        )
        validation = validate_step_output(raw_reply, required_tokens=step.required_tokens)
        if not validation.is_valid:
            raise RuntimeError("; ".join(validation.errors))
        cleaned = normalize_step_markdown(validation.clean_markdown)
        out_path = module_dir / f"{step.step_id}.md"
        out_path.write_text(cleaned, encoding="utf-8")
        return out_path

    def _prepare_chat(self, driver: Any, request: ChapterNoteRequest) -> None:
        """Initialize chat session, model, and source PDF upload on the driver.

        Args:
            driver: Active generation driver.
            request: Chapter note request.
        """
        chat_title = f"[{request.chapter_id}] {request.chapter_title}".strip()
        driver.open_chapter_chat(chat_title)
        if request.model:
            driver.set_model(request.model)
        if request.pdf_path is not None:
            driver.upload_files([request.pdf_path])
        driver.rename_chat(chat_title)

    def _execute_steps(
        self,
        request: ChapterNoteRequest,
        steps: list[NotePipelineStep],
        module_dir: Path,
        archive_dir: Path,
    ) -> list[str]:
        """Run all selected steps inside a driver session, tracking completed IDs.

        Args:
            request: Chapter note request.
            steps: Ordered pipeline steps.
            module_dir: Output directory for per-module `.md` files.
            archive_dir: Archive directory for existing module files.

        Returns:
            List of completed step IDs.
        """
        completed: list[str] = []
        with self._acquire_driver(request) as driver:
            self._prepare_chat(driver, request)
            for step in steps:
                if self.state.is_pause_requested(request.course_key):
                    raise GenerationPausedError("使用者已請求暫停生成。")
                _archive_existing_file(module_dir / f"{step.step_id}.md", archive_dir)
                self._run_step_with_policy(driver, step, request, module_dir)
                completed.append(step.step_id)
                self.state.update_chapter_state(
                    request.course_key,
                    request.chapter_id,
                    {"completed_steps": list(completed)},
                )
        return completed

    def run_chapter(self, request: ChapterNoteRequest) -> dict[str, Any]:
        """Run modular note generation for one chapter and stitch into `.md`.

        Args:
            request: Chapter generation parameters.

        Returns:
            Result summary with `status`, `stitched_path`, `completed_steps`, and `backend`.
        """
        request = self.paths.validated_request(request)
        self.state.clear_pause(request.course_key)
        notes_dir = self.paths.notes_course_dir(request.course_key, request.study_dir)
        module_dir = notes_dir / "modules" / request.chapter_id
        module_dir.mkdir(parents=True, exist_ok=True)
        stitched_path = self.paths.stitched_note_path(request)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_dir = notes_dir / "versions" / request.chapter_id / stamp

        _archive_existing_file(stitched_path, archive_dir)
        self.state.update_chapter_state(
            request.course_key,
            request.chapter_id,
            {"status": "in_progress", "backend": request.backend.value, "completed_steps": []},
        )
        try:
            completed = self._execute_steps(
                request, _select_steps(request.steps_override), module_dir, archive_dir
            )
        except (GenerationPausedError, QuotaExceededError) as exc:
            return self._record_interruption(request, exc)
        return self._stitch_chapter(request, module_dir, stitched_path, completed)

    def _record_interruption(
        self, request: ChapterNoteRequest, exc: GenerationPausedError | QuotaExceededError
    ) -> dict[str, Any]:
        """Persist a paused / quota-wait status after generation stopped early.

        Args:
            request: Chapter note request.
            exc: Pause or quota exception that stopped the run.

        Returns:
            Result summary with `status` and `error`.
        """
        status = "paused" if isinstance(exc, GenerationPausedError) else "quota_wait"
        logger.info("Note generation %s/%s stopped: %s", request.course_key, request.chapter_id, status)
        self.state.update_chapter_state(
            request.course_key, request.chapter_id, {"status": status, "last_error": str(exc)}
        )
        return {"status": status, "error": str(exc), "completed_steps": []}

    def _stitch_chapter(
        self, request: ChapterNoteRequest, module_dir: Path, stitched_path: Path, completed: list[str]
    ) -> dict[str, Any]:
        """Compose module files into the chapter `.md` and record the finished state.

        Args:
            request: Chapter note request.
            module_dir: Folder holding per-module `.md` files.
            stitched_path: Destination of the stitched chapter note.
            completed: Step IDs completed in this run.

        Returns:
            Result summary with `status`, `stitched_path`, `completed_steps`, and `backend`.
        """
        composed = compose_chapter_from_modules(module_dir, request.chapter_id, request.chapter_title)
        stitched_path.parent.mkdir(parents=True, exist_ok=True)
        stitched_path.write_text(composed, encoding="utf-8")
        self.state.update_chapter_state(
            request.course_key,
            request.chapter_id,
            {"status": "done", "stitched_path": str(stitched_path), "last_error": ""},
        )
        logger.info("Stitched chapter note %s -> %s", request.chapter_id, stitched_path)
        return {
            "status": "done",
            "backend": request.backend.value,
            "stitched_path": str(stitched_path),
            "completed_steps": completed,
        }

    def _run_step_with_policy(
        self,
        driver: Any,
        step: NotePipelineStep,
        request: ChapterNoteRequest,
        module_dir: Path,
    ) -> None:
        """Run one step and allow soft-fail steps to log a warning without aborting.

        Args:
            driver: Active generation driver.
            step: Pipeline step definition.
            request: Chapter note request.
            module_dir: Output directory for module `.md` files.
        """
        try:
            self._run_single_step(driver, step, request, module_dir)
        except (GenerationPausedError, QuotaExceededError):
            raise
        except Exception as exc:
            if step.soft_fail:
                logger.warning("Soft-fail step %s skipped: %s", step.step_id, exc)
                return
            self.state.update_chapter_state(
                request.course_key,
                request.chapter_id,
                {"status": "failed", "last_error": f"{step.step_id}: {exc}"},
            )
            raise

    def read_stitched_note(
        self,
        course_key: str,
        chapter_id: str,
        study_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Read the stitched Markdown note for a chapter if it exists.

        Args:
            course_key: Course identifier.
            chapter_id: Chapter identifier (e.g. `ch01`).
            study_dir: Optional explicit course study directory.

        Returns:
            Dictionary with `exists`, `path`, and `content`.
        """
        validate_path_segment(chapter_id, "chapter_id")
        course_dir = self.paths.notes_course_dir(course_key, study_dir)
        matches = sorted(course_dir.glob(f"{chapter_id}_*_學習筆記.md")) if course_dir.is_dir() else []
        if not matches:
            return {"exists": False, "path": "", "content": ""}
        target = matches[0]
        return {"exists": True, "path": str(target), "content": target.read_text(encoding="utf-8")}

    def list_chapters(self, course_key: str, study_dir: Path | None = None) -> list[dict[str, Any]]:
        """List stitched chapter `.md` notes for a course.

        Args:
            course_key: Course identifier.
            study_dir: Optional explicit course study directory.

        Returns:
            List of chapter note metadata dicts.
        """
        return list_chapter_notes(self.paths.notes_course_dir(course_key, study_dir))

    def push_to_source(
        self,
        course_key: str,
        chapter_id: str,
        notebook_id: str,
        upload_fn: Callable[[str, str], str],
    ) -> dict[str, Any]:
        """Render a chapter `.md` note to PDF and upload it to Gemini Notebook.

        Args:
            course_key: Course identifier.
            chapter_id: Chapter identifier (e.g. `ch01`).
            notebook_id: Target Gemini Notebook ID.
            upload_fn: Synchronous upload callback `(notebook_id, pdf_path) -> source_id`.

        Returns:
            Upload result dictionary with `source_id`.
        """
        validate_path_segment(chapter_id, "chapter_id")
        return push_chapter_note_to_source(
            self.paths.notes_course_dir(course_key), chapter_id, notebook_id, upload_fn
        )

    def import_legacy(
        self,
        source_dir: Path,
        course_key: str,
        overwrite: bool = False,
        study_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Import `.md` notes from a standalone `note-studio` folder into `03 Notes/NoteStudio`.

        Args:
            source_dir: Source folder containing `.md` files.
            course_key: Target course identifier.
            overwrite: Whether to overwrite existing files.
            study_dir: Optional explicit course study directory.

        Returns:
            Import summary dictionary.
        """
        checked_source = self.paths.checked_legacy_source_dir(source_dir)
        return import_legacy_notes(
            checked_source, self.paths.notes_course_dir(course_key, study_dir), overwrite=overwrite
        )

"""Phase 1 modular Markdown note generation service (Refs: ADR-012).

Orchestrates prompt loading from standalone `.md` templates, dual-backend
generation (`gemini_web` primary and `notebooklm` fallback) via injected
driver factories, step validation, version archiving, and chapter `.md` stitching.
"""

from __future__ import annotations

import logging
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generator

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.note_pipeline import (
    STANDARD_NOTE_STEPS,
    DriverUnavailableError,
    GenerationPausedError,
    NoteBackend,
    NotePipelineStep,
    QuotaExceededError,
)
from notebooklm_batch_studio.domain.study_hierarchy import resolve_note_studio_dir
from notebooklm_batch_studio.services.notes.chapter_normalizer import normalize_step_markdown
from notebooklm_batch_studio.services.notes.module_composer import compose_chapter_from_modules
from notebooklm_batch_studio.services.notes.module_prompts import (
    StepPromptContext,
    list_module_prompt_specs,
    load_module_prompt,
)
from notebooklm_batch_studio.services.notes.state_manager import NoteStateManager
from notebooklm_batch_studio.services.notes.step_validator import validate_step_output

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChapterNoteRequest:
    """Parameters for generating or rerunning one chapter's Markdown notes.

    Attributes:
        course_key: Course identifier or folder code.
        course_name: Human-readable course name filled into `{{COURSE_NAME}}`.
        chapter_id: Chapter identifier such as `ch01`.
        chapter_title: Chapter title filled into `{{CHAPTER_TITLE}}`.
        pdf_path: Optional chapter PDF path (used by `gemini_web` upload).
        backend: Generation backend (`gemini_web` default, `notebooklm` fallback).
        model: Gemini model name (e.g. `4 Argon`).
        notebook_id: Target NotebookLM ID when `backend == notebooklm`.
        source_ids: Single-chapter NotebookLM source IDs when `backend == notebooklm`.
        steps_override: Optional subset of step IDs for single-module rerun.
        study_dir: Optional course study directory (`<study_root>/<term>/<subject>`).
    """

    course_key: str
    course_name: str
    chapter_id: str
    chapter_title: str = ""
    pdf_path: Path | None = None
    backend: NoteBackend = NoteBackend.GEMINI_WEB
    model: str = "4 Argon"
    notebook_id: str = ""
    source_ids: list[str] = field(default_factory=list)
    steps_override: list[str] | None = None
    study_dir: Path | None = None


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
    ) -> None:
        """Initialize the note pipeline service.

        Args:
            config: Immutable application configuration.
            driver_factory: Factory returning a context manager yielding a driver.
            study_dir_resolver: Optional callback resolving `course_key -> study_dir`.
        """
        self.config = config
        self._driver_factory = driver_factory
        self._study_dir_resolver = study_dir_resolver
        self.state = NoteStateManager(config.state_dir / "notes")
        self.override_prompt_dir = config.data_dir / "prompts" / "modular_specs"

    def _notes_course_dir(self, course_key: str, study_dir: Path | None = None) -> Path:
        """Return `<study_dir>/03 Notes/NoteStudio`, or `<scratch_dir>/notes/<course_key>` if unlinked.

        Args:
            course_key: Course identifier.
            study_dir: Optional explicit course study directory.

        Returns:
            Path inside `03 Notes/NoteStudio`, or `scratch/notes/<course_key>` when no study_dir exists.
        """
        resolved = study_dir or (self._study_dir_resolver(course_key) if self._study_dir_resolver else None)
        if resolved is not None:
            return resolve_note_studio_dir(resolved)
        return self.config.scratch_dir / "notes" / course_key

    def _stitched_note_path(self, request: ChapterNoteRequest) -> Path:
        """Return the canonical stitched `.md` path for a chapter.

        Args:
            request: Chapter note generation request.

        Returns:
            Path to `<chapter_id>_<title>_學習筆記.md` inside `03 Notes/NoteStudio`.
        """
        title = request.chapter_title.strip() or request.chapter_id
        safe_title = title.replace("/", "_").replace("\\", "_")
        notes_dir = self._notes_course_dir(request.course_key, request.study_dir)
        return notes_dir / f"{request.chapter_id}_{safe_title}_學習筆記.md"

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
        self.state.request_pause(course_key)
        return {"course_key": course_key, "paused": True}

    def clear_pause(self, course_key: str) -> dict[str, Any]:
        """Clear any active pause request for a course.

        Args:
            course_key: Course identifier.

        Returns:
            Updated status summary.
        """
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
        self.state.clear_pause(request.course_key)
        steps = _select_steps(request.steps_override)
        notes_dir = self._notes_course_dir(request.course_key, request.study_dir)
        module_dir = notes_dir / "modules" / request.chapter_id
        module_dir.mkdir(parents=True, exist_ok=True)
        stitched_path = self._stitched_note_path(request)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_dir = notes_dir / "versions" / request.chapter_id / stamp

        _archive_existing_file(stitched_path, archive_dir)
        self.state.update_chapter_state(
            request.course_key,
            request.chapter_id,
            {"status": "in_progress", "backend": request.backend.value, "completed_steps": []},
        )
        try:
            completed = self._execute_steps(request, steps, module_dir, archive_dir)
        except (GenerationPausedError, QuotaExceededError) as exc:
            status = "paused" if isinstance(exc, GenerationPausedError) else "quota_wait"
            self.state.update_chapter_state(
                request.course_key, request.chapter_id, {"status": status, "last_error": str(exc)}
            )
            return {"status": status, "error": str(exc), "completed_steps": []}

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
        course_dir = self._notes_course_dir(course_key, study_dir)
        matches = sorted(course_dir.glob(f"{chapter_id}_*_學習筆記.md")) if course_dir.is_dir() else []
        if not matches:
            return {"exists": False, "path": "", "content": ""}
        target = matches[0]
        return {"exists": True, "path": str(target), "content": target.read_text(encoding="utf-8")}

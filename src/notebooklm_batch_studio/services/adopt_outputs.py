"""Adopt pre-existing local NotebookLM outputs into done artifact_jobs (Refs: SPEC-015)."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import ArtifactJob, ArtifactType, JobStatus
from notebooklm_batch_studio.domain.naming import label_for
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol, QueueRepositoryProtocol
from notebooklm_batch_studio.domain.study_hierarchy import resolve_course_output_root
from notebooklm_batch_studio.services.artifact_runner import (
    MIND_MAP_TYPES,
    REPORT_FORMATS,
    SIMPLE_OUTPUTS,
)
from notebooklm_batch_studio.services.converters.image_fitter import DEVICE_TARGETS
from notebooklm_batch_studio.services.quiz_runner import MOCK_EXAM_TYPES, QUIZ_TYPES

logger = logging.getLogger(__name__)

_RE_LECTURE_DIR = re.compile(r"^(\d+)_")


@dataclass(frozen=True)
class _MatchedArtifact:
    """Internal representation of one matched local artifact deliverable."""

    artifact_type: ArtifactType
    output_file: Path
    interactive_path: Path | None = None


def _collect_target_dirs(output_root: Path) -> list[tuple[int | None, Path]]:
    """Collect sorted lecture folders (`NN_*`) and `_course_synthesis` under `output_root`.

    Args:
        output_root: Resolved course NotebookLM output root directory.

    Returns:
        List of `(lecture_no_or_none, folder_path)` sorted by lecture number then synthesis.
    """
    if not output_root.is_dir():
        return []
    targets: list[tuple[int | None, Path]] = []
    for entry in output_root.iterdir():
        if entry.is_symlink() or not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name == "_course_synthesis":
            targets.append((None, entry))
            continue
        match = _RE_LECTURE_DIR.match(entry.name)
        if match:
            targets.append((int(match.group(1)), entry))
    return sorted(targets, key=lambda item: (item[0] is None, item[0] or 0, item[1].name))


def _list_visible_files(folder: Path) -> dict[str, Path]:
    """Return sorted visible non-symlink filename-to-Path map inside `folder`.

    Args:
        folder: Directory containing generated artifact files.

    Returns:
        Dictionary mapping filenames to `Path` objects.
    """
    return {
        p.name: p
        for p in sorted(folder.iterdir(), key=lambda p: p.name)
        if p.is_file() and not p.is_symlink() and not p.name.startswith(".")
    }


def _match_audio(
    files: dict[str, Path], claimed: set[str], lecture_no: int | None
) -> _MatchedArtifact | None:
    """Match an audio overview `.m4a` file for lecture or course-synthesis scope.

    Args:
        files: Directory filename-to-path map.
        claimed: Mutable set of claimed filenames in this folder.
        lecture_no: Sequence number or None for `_course_synthesis`.

    Returns:
        `_MatchedArtifact` when matched, otherwise None.
    """
    if lecture_no is None:
        match = next((n for n in files if n not in claimed and n.endswith("_course_audio.m4a")), None)
        if match is None:
            return None
        claimed.add(match)
        return _MatchedArtifact(ArtifactType.COURSE_AUDIO, files[match])

    suffixes = (f"_L{lecture_no:02d}_audio.m4a", f"_L{lecture_no}_audio.m4a")
    match = next(
        (n for n in files if n not in claimed and any(n.endswith(suf) for suf in suffixes)),
        None,
    )
    if match is None:
        match = next(
            (n for n in files if n not in claimed and n.endswith("_audio.m4a") and "_course_audio" not in n),
            None,
        )
    if match is None:
        return None
    claimed.add(match)
    return _MatchedArtifact(ArtifactType.AUDIO, files[match])


def _match_quizzes(files: dict[str, Path], claimed: set[str], is_course: bool) -> list[_MatchedArtifact]:
    """Match quiz or mock-exam artifact groups using `QUIZ_TYPES` / `MOCK_EXAM_TYPES`.

    Args:
        files: Directory filename-to-path map.
        claimed: Mutable set of claimed filenames in this folder.
        is_course: True when scanning `_course_synthesis`.

    Returns:
        List of matched quiz/mock-exam `_MatchedArtifact` entries.
    """
    matched: list[_MatchedArtifact] = []
    types = MOCK_EXAM_TYPES if is_course else QUIZ_TYPES
    for art_type in types:
        prefix = f"{art_type.value}_"
        companions = (
            f"{prefix}quiz.json",
            f"{prefix}interactive_quiz.html",
            f"{prefix}題目卷.md",
            f"{prefix}答案卷.md",
            f"{prefix}題目卷.pdf",
            f"{prefix}答案卷.pdf",
        )
        primary_name = f"{prefix}quiz.json" if f"{prefix}quiz.json" in files else f"{prefix}題目卷.md"
        if primary_name not in files:
            continue
        claimed.update(name for name in companions if name in files)
        inter_path = files.get(f"{prefix}interactive_quiz.html")
        matched.append(_MatchedArtifact(art_type, files[primary_name], inter_path))
    if matched:
        claimed.update(compat for compat in ("quiz.json", "答案卷.md") if compat in files)
    return matched


def _match_flashcards_and_mindmap(
    files: dict[str, Path], claimed: set[str], is_course: bool
) -> list[_MatchedArtifact]:
    """Match flashcards and mind-map deliverable groups reusing `MIND_MAP_TYPES`.

    Args:
        files: Directory filename-to-path map.
        claimed: Mutable set of claimed filenames in this folder.
        is_course: True when scanning `_course_synthesis`.

    Returns:
        List of matched `_MatchedArtifact` entries.
    """
    matched: list[_MatchedArtifact] = []
    if not is_course and ("anki.csv" in files or "flashcards.json" in files):
        primary = files["anki.csv"] if "anki.csv" in files else files["flashcards.json"]
        claimed.update(name for name in ("anki.csv", "flashcards.json") if name in files)
        matched.append(_MatchedArtifact(ArtifactType.FLASHCARDS, primary))

    mm_candidates = ("mindmap.opml", "mindmap.json", "mindmap.md")
    present_mm = [name for name in mm_candidates if name in files]
    if present_mm:
        mm_type = MIND_MAP_TYPES[1] if is_course else MIND_MAP_TYPES[0]
        claimed.update(present_mm)
        matched.append(_MatchedArtifact(mm_type, files[present_mm[0]]))
    return matched


def _match_reports(
    files: dict[str, Path], claimed: set[str], lecture_no: int | None
) -> list[_MatchedArtifact]:
    """Match generated report `.md` files and companion HTML using `REPORT_FORMATS`.

    Args:
        files: Directory filename-to-path map.
        claimed: Mutable set of claimed filenames in this folder.
        lecture_no: Sequence number or None for `_course_synthesis`.

    Returns:
        List of matched report `_MatchedArtifact` entries.
    """
    is_course = lecture_no is None
    matched: list[_MatchedArtifact] = []
    for art_type, fmt in REPORT_FORMATS.items():
        if art_type.value.startswith("course_") != is_course:
            continue
        suffixes = (
            (f"_Course_{fmt}.md",)
            if is_course
            else (f"_L{lecture_no}_{fmt}.md", f"_L{lecture_no:02d}_{fmt}.md")
        )
        name = next(
            (n for n in files if n not in claimed and any(n.endswith(suf) for suf in suffixes)),
            None,
        )
        if name is None:
            continue
        claimed.add(name)
        inter_name = f"{files[name].stem}_interactive.html"
        inter_path = files.get(inter_name)
        if inter_path is not None:
            claimed.add(inter_name)
        matched.append(_MatchedArtifact(art_type, files[name], inter_path))
    return matched


def _claim_infographic_devices(files: dict[str, Path], claimed: set[str], stem: str) -> None:
    """Claim device-fitted infographic exports named via `DEVICE_TARGETS`.

    Args:
        files: Directory filename-to-path map.
        claimed: Mutable set of claimed filenames in this folder.
        stem: Base infographic stem (e.g. `infographic`).
    """
    for target in DEVICE_TARGETS:
        dev_name = f"{stem}_{target.suffix}{target.extension}"
        if dev_name in files:
            claimed.add(dev_name)


def _match_simple_outputs(
    files: dict[str, Path], claimed: set[str], is_course: bool
) -> list[_MatchedArtifact]:
    """Match single-shot artifacts using `SIMPLE_OUTPUTS` and `DEVICE_TARGETS`.

    Args:
        files: Directory filename-to-path map.
        claimed: Mutable set of claimed filenames in this folder.
        is_course: True when scanning `_course_synthesis`.

    Returns:
        List of matched simple-output `_MatchedArtifact` entries.
    """
    matched: list[_MatchedArtifact] = []
    for art_type, (kind, lecture_name, course_name) in SIMPLE_OUTPUTS.items():
        if art_type.value.startswith("course_") != is_course:
            continue
        base_name = course_name if is_course else lecture_name
        candidates = [base_name]
        if kind == "slide_deck":
            candidates.append(base_name.removesuffix(".pdf") + ".pptx")
        hit = next((cand for cand in candidates if cand in files and cand not in claimed), None)
        if hit is None:
            continue
        claimed.add(hit)
        if kind == "infographic":
            _claim_infographic_devices(files, claimed, files[hit].stem)
        matched.append(_MatchedArtifact(art_type, files[hit]))
    return matched


def _scan_folder_artifacts(folder: Path, lecture_no: int | None) -> tuple[list[_MatchedArtifact], list[str]]:
    """Match all known artifact deliverables in one folder and collect unmapped filenames.

    Args:
        folder: Directory path (`<NN>_<slug>` or `_course_synthesis`).
        lecture_no: Integer lecture number, or None for `_course_synthesis`.

    Returns:
        Tuple of `(matched_artifacts, unmapped_filenames)`.
    """
    files = _list_visible_files(folder)
    claimed: set[str] = set()
    is_course = lecture_no is None
    matched: list[_MatchedArtifact] = []

    audio = _match_audio(files, claimed, lecture_no)
    if audio is not None:
        matched.append(audio)
    matched.extend(_match_quizzes(files, claimed, is_course))
    matched.extend(_match_flashcards_and_mindmap(files, claimed, is_course))
    matched.extend(_match_reports(files, claimed, lecture_no))
    matched.extend(_match_simple_outputs(files, claimed, is_course))
    matched.sort(key=lambda item: item.artifact_type.value)

    return matched, [name for name in files if name not in claimed]


def _make_adopted_job(course_code: str, lecture_no: int | None, item: _MatchedArtifact) -> ArtifactJob:
    """Construct a DONE `ArtifactJob` representing an existing local file.

    Args:
        course_code: Registered course identifier.
        lecture_no: Lecture sequence number or None for course synthesis.
        item: Matched local deliverable metadata.

    Returns:
        Unsaved `ArtifactJob` ready to persist via `QueueRepository`.
    """
    return ArtifactJob(
        id=str(uuid.uuid4()),
        course_code=course_code,
        lecture_no=lecture_no,
        artifact_type=item.artifact_type,
        status=JobStatus.DONE,
        version=1,
        output_file=str(item.output_file),
        interactive_path=str(item.interactive_path) if item.interactive_path else None,
        source_origin="adopted",
    )


def _match_row_dict(item: _MatchedArtifact, *, is_skip: bool) -> dict[str, Any]:
    """Serialize one matched deliverable row for dry-run and apply responses.

    Args:
        item: Matched local deliverable metadata.
        is_skip: True when a matching job already exists in DB.

    Returns:
        Dictionary describing the matched deliverable and planned status.
    """
    return {
        "artifact_type": item.artifact_type.value,
        "label": label_for(item.artifact_type),
        "output_file": str(item.output_file),
        "interactive_path": str(item.interactive_path) if item.interactive_path else None,
        "status": "skip" if is_skip else "create",
    }


def _build_folder_plan(
    course_code: str,
    folder: Path,
    lecture_no: int | None,
    existing_keys: set[tuple[int | None, ArtifactType]],
) -> tuple[dict[str, Any], list[ArtifactJob], int]:
    """Scan one output directory and assemble preview rows and new `ArtifactJob` objects.

    Args:
        course_code: Target course identifier.
        folder: Subdirectory (`<NN>_<slug>` or `_course_synthesis`).
        lecture_no: Lecture sequence number or None for course synthesis.
        existing_keys: Existing `(lecture_no, artifact_type)` pairs in DB.

    Returns:
        Tuple of `(lecture_entry_dict, pending_new_jobs, skip_count)`.
    """
    matched, unmapped = _scan_folder_artifacts(folder, lecture_no)
    new_jobs: list[ArtifactJob] = []
    rows: list[dict[str, Any]] = []
    skip_count = 0
    for item in matched:
        is_skip = (lecture_no, item.artifact_type) in existing_keys
        skip_count += int(is_skip)
        if not is_skip:
            new_jobs.append(_make_adopted_job(course_code, lecture_no, item))
        rows.append(_match_row_dict(item, is_skip=is_skip))
    entry = {"lecture_no": lecture_no, "folder": folder.name, "matched": rows, "unmapped_files": unmapped}
    return entry, new_jobs, skip_count


class AdoptOutputsService:
    """Service scanning local NotebookLM output folders to adopt done jobs without API calls."""

    def __init__(
        self,
        config: AppConfig,
        course_repo: CourseRepositoryProtocol,
        queue_repo: QueueRepositoryProtocol,
    ) -> None:
        """Bind configuration and persistence repositories.

        Args:
            config: Loaded application configuration.
            course_repo: Course metadata repository.
            queue_repo: Artifact job queue repository.
        """
        self.config = config
        self.course_repo = course_repo
        self.queue_repo = queue_repo

    def _collect_plan(
        self, course_code: str, output_root: Path
    ) -> tuple[list[dict[str, Any]], list[ArtifactJob], list[str], int]:
        """Scan all target folders under `output_root` and aggregate plan rows.

        Args:
            course_code: Registered course identifier.
            output_root: Course NotebookLM output root directory.

        Returns:
            Tuple of `(lecture_entries, new_jobs, all_unmapped, skip_count)`.
        """
        existing_keys = {
            (j.lecture_no, j.artifact_type) for j in self.queue_repo.list_jobs(course_code=course_code)
        }
        lectures_out: list[dict[str, Any]] = []
        all_unmapped: list[str] = []
        new_jobs: list[ArtifactJob] = []
        would_skip = 0
        for lecture_no, folder in _collect_target_dirs(output_root):
            entry, jobs, skips = _build_folder_plan(course_code, folder, lecture_no, existing_keys)
            lectures_out.append(entry)
            new_jobs.extend(jobs)
            would_skip += skips
            all_unmapped.extend(f"{folder.name}/{name}" for name in entry["unmapped_files"])
        return lectures_out, new_jobs, all_unmapped, would_skip

    def adopt_existing_outputs(self, code: str, dry_run: bool = True) -> dict[str, Any]:
        """Adopt existing local NotebookLM deliverables into done `artifact_jobs` rows.

        Args:
            code: Registered course identifier.
            dry_run: Preview matched/unmapped counts without writing DB when True.

        Returns:
            Summary payload with per-folder matches, `unmapped_files`, and job counters.

        Raises:
            CourseNotFoundError: When `code` is not registered.
        """
        course = self.course_repo.get_course(code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {code}")

        output_root = resolve_course_output_root(
            self.config.courses_output_dir, course.code, course.study_dir
        )
        lectures_out, new_jobs, all_unmapped, would_skip = self._collect_plan(course.code, output_root)
        created = self.queue_repo.enqueue_jobs(new_jobs) if (not dry_run and new_jobs) else 0
        logger.info(
            "Adopt outputs course=%s dry_run=%s create=%d skip=%d",
            course.code,
            dry_run,
            len(new_jobs),
            would_skip,
        )
        return {
            "course_code": course.code,
            "dry_run": dry_run,
            "output_root": str(output_root),
            "lectures": lectures_out,
            "unmapped_files": all_unmapped,
            "would_create": len(new_jobs),
            "would_skip": would_skip,
            "created": created,
            "skipped": would_skip if not dry_run else 0,
        }

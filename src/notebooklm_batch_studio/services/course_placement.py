"""Place external course folders into `DATA_DIR/study/<term>/<folder>/` and upload optional textbooks."""

from __future__ import annotations

import dataclasses
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.config.study_layout import CategoryRole
from notebooklm_batch_studio.domain.course_identity import make_course_code, parse_course_folder
from notebooklm_batch_studio.domain.models import Course, ProfileName
from notebooklm_batch_studio.domain.path_safety import ensure_within_roots, is_within, validate_path_segment
from notebooklm_batch_studio.domain.repositories import NotebookLMClientProtocol
from notebooklm_batch_studio.services.course_parser import scan_course_directory

logger = logging.getLogger(__name__)


def build_study_folder_name(course_no: str, course_name: str) -> str:
    """Format canonical `study/<term>/` course directory name from course number and title.

    Args:
        course_no: Normalized uppercase course number (e.g. `CP30000`).
        course_name: Human-readable course name (e.g. `團體諮商`).

    Returns:
        Safe directory basename such as `CP__30000-團體諮商`.
    """
    match = re.match(r"^([A-Za-z]{1,6})([0-9][0-9A-Za-z]*)$", course_no)
    prefix = f"{match.group(1)}__{match.group(2)}" if match else course_no
    return validate_path_segment(f"{prefix}-{course_name}", "course_folder")


def _copy_pdfs_to_handouts(src: Path, handouts_dir: Path) -> int:
    """Copy visible PDF files from an external folder into `02 Handouts/` without modifying src.

    Args:
        src: Source directory outside `study_root_dir`.
        handouts_dir: Destination `HANDOUTS` category directory inside `study/`.

    Returns:
        Count of copied PDF files.
    """
    copied = 0
    for pdf in sorted(src.rglob("*"), key=lambda p: str(p).lower()):
        if not pdf.is_file() or pdf.name.startswith(".") or pdf.suffix.lower() != ".pdf":
            continue
        rel = pdf.relative_to(src)
        dest = handouts_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, dest)
        copied += 1
    return copied


def _ensure_course_tree(folder: Path, config: AppConfig) -> None:
    """Create the missing 01–05 folders of a course folder created or pasted as study/<term>/<course>/.

    Existing files are never moved; deeper folders inside a course are left alone (SPEC-027).

    Args:
        folder: Folder inside `study/`.
        config: Application config providing `study_root_dir` and `study_layout`.
    """
    if folder.resolve().parent.parent == config.study_root_dir.resolve():
        config.study_layout.ensure_tree(folder)


def place_course_folder_in_study(src: Path, config: AppConfig, metadata: dict[str, str]) -> Path:
    """Place an external folder into `DATA_DIR/study/<term>/<folder>/02 Handouts/` when metadata is set.

    Folders inside `study/` stay in place (missing 01–05 are created, SPEC-027). External folders without
    `term`/`course_no` also pass through untouched to preserve legacy CLI/test behavior.

    Args:
        src: Resolved source folder path.
        config: Application config providing `study_root_dir` and `study_layout`.
        metadata: Optional keys `term`, `course_no`, and `course_name`.

    Returns:
        Course root directory inside `study/` (if placed) or original `src`.

    Raises:
        ValueError: When `term` is given without a resolvable `course_no`.
    """
    if is_within(src, config.study_root_dir):
        _ensure_course_tree(src, config)
        return src
    term = (metadata.get("term") or "").strip().replace("_", "-")
    raw_no = (metadata.get("course_no") or "").strip()
    if not term and not raw_no:
        return src

    info = parse_course_folder(src.name)
    clean_no = re.sub(r"[^A-Za-z0-9]", "", raw_no or info.course_no).upper()
    if not clean_no:
        raise ValueError("請提供課號（course_no）才能歸入 study/ 目錄")
    make_course_code(term, clean_no)
    course_name = (metadata.get("course_name") or "").strip() or (info.name if info.is_course else src.name)
    folder_name = build_study_folder_name(clean_no, course_name)

    target_dir = config.study_root_dir / term / folder_name
    ensure_within_roots(target_dir, [config.study_root_dir], "study course directory")
    config.study_layout.ensure_tree(target_dir)
    handouts_dir = config.study_layout.primary_dir(target_dir, CategoryRole.HANDOUTS)
    copied = _copy_pdfs_to_handouts(src, handouts_dir)
    logger.info("Placed %d PDFs from %s into %s", copied, src, handouts_dir)
    return target_dir


def prepare_course_for_registration(
    raw_path: str, prof_enum: ProfileName, opts: dict[str, Any], config: AppConfig
) -> Course:
    """Place an external folder into `study/` when needed, scan PDFs, and build a Course.

    Args:
        raw_path: Filesystem path string for the course folder.
        prof_enum: Resolved `ProfileName` enum.
        opts: Registration keyword options (`term`, `course_no`, `course_name`, etc.).
        config: Application configuration providing `study_root_dir` and `study_layout`.

    Returns:
        Configured `Course` entity ready to persist.
    """
    path = Path(raw_path).expanduser().resolve()
    meta = {k: str(opts.get(k) or "") for k in ("term", "course_no", "course_name")}
    target_path = place_course_folder_in_study(path, config, meta)
    scanned = scan_course_directory(target_path, term=meta["term"], layout=config.study_layout)
    return dataclasses.replace(
        scanned,
        profile=prof_enum,
        language=str(opts.get("language", "zh-TW")),
        selected_chapter_artifacts=opts.get("chapter_artifacts") or [],
        selected_course_artifacts=opts.get("course_artifacts") or [],
        paused=bool(opts.get("paused", False)),
        reuse_notebook=bool(opts.get("reuse_notebook", True)),
    )


async def upload_material_sources(
    client: NotebookLMClientProtocol,
    notebook_id: str,
    pdf_paths: list[Path],
    existing_sources: dict[str, str],
) -> None:
    """Upload opt-in `01 Materials` textbook PDFs into a course's Gemini Notebook.

    Args:
        client: Remote Gemini Notebook adapter client.
        notebook_id: Target remote notebook identifier.
        pdf_paths: Textbook/material PDF paths returned by `list_material_source_pdfs`.
        existing_sources: Existing remote source mapping keyed by filename.
    """
    for pdf in pdf_paths:
        if pdf.name in existing_sources:
            logger.info("Material source %s already exists in notebook %s", pdf.name, notebook_id)
            continue
        source_id = await client.upload_source(notebook_id, str(pdf))
        await client.wait_source_ready(notebook_id, source_id)
        logger.info("Uploaded material textbook %s -> source %s", pdf.name, source_id)

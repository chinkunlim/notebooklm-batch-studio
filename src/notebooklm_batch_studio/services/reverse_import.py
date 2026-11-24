"""Reverse import service: lists remote Gemini Notebooks, previews contents, and downloads all files locally.

Allows users who already have notebooks in Gemini Notebook (NotebookLM) to optionally import
an existing notebook as a local course and download both its remote sources (as Markdown) and
remote artifacts into DATA_DIR so every file is available offline in Study Workbench.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notebooklm_batch_studio.config.settings import AppConfig
from notebooklm_batch_studio.domain.course_identity import TERM_PATTERN, make_course_code, split_course_code
from notebooklm_batch_studio.domain.models import Course, CourseStatus, Lecture, ProfileName
from notebooklm_batch_studio.domain.path_safety import ensure_within_roots
from notebooklm_batch_studio.domain.repositories import (
    CourseRepositoryProtocol,
    NotebookLMClientProtocol,
    QueueRepositoryProtocol,
)
from notebooklm_batch_studio.domain.study_hierarchy import resolve_course_output_root
from notebooklm_batch_studio.domain.study_layout import DEFAULT_LAYOUT, CategoryRole, StudyLayout
from notebooklm_batch_studio.services.course_placement import build_study_folder_name
from notebooklm_batch_studio.services.sync_service import RemoteSyncService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReverseImportOptions:
    """Options controlling an optional reverse import from a remote Gemini Notebook.

    Attributes:
        notebook_id: Remote Gemini Notebook identifier.
        term: Required academic term matching `TERM_PATTERN` (e.g. `113-2`).
        course_no: Optional school course number (e.g. `CP30000`).
        course_code: Optional legacy/custom course code hint.
        course_name: Optional local course title (defaults to remote notebook title).
        language: Output language code for future local generations.
        record_only: True to import as `record-only` + `archived` without scheduling jobs.
        download_sources: Whether to download remote source fulltext locally as Markdown.
        download_artifacts: Whether to download remote artifacts locally.
        source_ids: Optional subset of remote source IDs to download (None = all).
        artifact_ids: Optional subset of remote artifact IDs to download (None = all).
    """

    notebook_id: str
    term: str = ""
    course_no: str = ""
    course_code: str | None = None
    course_name: str | None = None
    language: str = "zh-TW"
    record_only: bool = True
    download_sources: bool = True
    download_artifacts: bool = True
    source_ids: list[str] | None = None
    artifact_ids: list[str] | None = None


def _sanitize_filename(name: str, fallback: str) -> str:
    """Sanitize a remote title into a safe local filename stem.

    Args:
        name: Raw remote title.
        fallback: Fallback stem if sanitized result is empty.

    Returns:
        Safe filename stem without path separators.
    """
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "_", (name or "").strip()).strip(". ")
    return cleaned[:80] if cleaned else fallback


def _derive_course_code(title: str, existing_codes: set[str]) -> str:
    """Derive a unique uppercase course code from a notebook title.

    Args:
        title: Remote notebook title.
        existing_codes: Set of course codes already in the local repository.

    Returns:
        Unique course code string.
    """
    ascii_tokens = re.findall(r"[A-Za-z0-9]+", title.upper())
    base = "".join(ascii_tokens)[:12] or f"NB_{hashlib.sha1(title.encode('utf-8')).hexdigest()[:6].upper()}"
    candidate = base
    idx = 2
    while candidate in existing_codes:
        candidate = f"{base}_{idx}"
        idx += 1
    return candidate


def _write_source_markdown(
    dest_dir: Path, idx: int, source: dict[str, Any], fulltext: dict[str, Any]
) -> tuple[Path, str]:
    """Write a downloaded remote source fulltext to a local Markdown file.

    Args:
        dest_dir: Target local directory under DATA_DIR.
        idx: 1-based lecture sequence number.
        source: Normalized source metadata dictionary.
        fulltext: Fulltext payload returned by `get_source_fulltext`.

    Returns:
        Tuple of (written file Path, SHA-256 hex digest).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    title = str(fulltext.get("title") or source.get("title") or f"source_{idx}")
    stem = _sanitize_filename(title, f"source_{idx:02d}")
    filename = f"{idx:02d}_{stem}.md" if not stem.lower().endswith(".md") else f"{idx:02d}_{stem}"
    target = dest_dir / filename
    body = str(fulltext.get("content") or "").strip()
    url = fulltext.get("url")
    header = f"# {title}\n\n" + (f"> Source URL: {url}\n\n" if url else "")
    content_text = header + (body if body else "_（遠端來源無純文字內容）_") + "\n"
    target.write_text(content_text, encoding="utf-8")
    digest = hashlib.sha256(content_text.encode("utf-8")).hexdigest()
    return target, digest


class ReverseImportService:
    """Orchestrates listing, previewing, and reverse-importing remote Gemini Notebooks locally."""

    def __init__(
        self,
        notebooklm_client: NotebookLMClientProtocol,
        course_repo: CourseRepositoryProtocol,
        queue_repo: QueueRepositoryProtocol,
        output_base_dir: Path,
    ) -> None:
        """Initialize the reverse import service.

        Args:
            notebooklm_client: Adapter client for Gemini Notebook API calls.
            course_repo: Course repository for local persistence.
            queue_repo: Queue repository for recording synced artifact jobs.
            output_base_dir: Base DATA_DIR path for local files.
        """
        self.client = notebooklm_client
        self.course_repo = course_repo
        self.queue_repo = queue_repo
        self.output_base_dir = output_base_dir
        self.study_root = output_base_dir.parent / "study"
        self.scratch_unarchived = output_base_dir.parent / "scratch" / "unarchived"
        self.study_layout: StudyLayout = DEFAULT_LAYOUT
        self.sync_service = RemoteSyncService(notebooklm_client, course_repo, queue_repo, output_base_dir)

    @classmethod
    def from_config(
        cls,
        notebooklm_client: NotebookLMClientProtocol,
        course_repo: CourseRepositoryProtocol,
        queue_repo: QueueRepositoryProtocol,
        config: AppConfig,
    ) -> ReverseImportService:
        """Build a `ReverseImportService` configured with `AppConfig` study paths and layout.

        Args:
            notebooklm_client: Adapter client for Gemini Notebook API calls.
            course_repo: Course repository for local persistence.
            queue_repo: Queue repository for recording synced artifact jobs.
            config: Application configuration providing study root, scratch paths, and layout.

        Returns:
            Configured `ReverseImportService` instance.
        """
        instance = cls(notebooklm_client, course_repo, queue_repo, config.output_dir)
        instance.study_root = config.study_root_dir
        instance.scratch_unarchived = config.scratch_kind_dir("unarchived")
        instance.study_layout = config.study_layout
        return instance

    async def list_remote_notebooks(self) -> list[dict[str, Any]]:
        """List remote Gemini Notebooks and annotate which ones are already linked locally.

        Returns:
            List of remote notebook dicts with `linked_course_code` and `linked_course_name`.
        """
        notebooks = await self.client.list_notebooks()
        local_courses = self.course_repo.list_courses()
        by_nb_id = {c.notebook_id: c for c in local_courses if c.notebook_id}
        enriched: list[dict[str, Any]] = []
        for nb in notebooks:
            linked = by_nb_id.get(nb["id"])
            enriched.append(
                {
                    **nb,
                    "linked_course_code": linked.code if linked else None,
                    "linked_course_name": linked.name if linked else None,
                }
            )
        return enriched

    async def preview_remote_notebook(self, notebook_id: str) -> dict[str, Any]:
        """Inspect a remote notebook's sources and artifacts before importing.

        Args:
            notebook_id: Remote Gemini Notebook identifier.

        Returns:
            Dictionary with notebook metadata, remote sources list, and remote artifacts list.
        """
        notebooks = await self.list_remote_notebooks()
        nb_meta = next(
            (n for n in notebooks if n["id"] == notebook_id), {"id": notebook_id, "title": notebook_id}
        )
        sources = await self.client.list_sources(notebook_id)
        artifacts = await self.client.list_artifacts(notebook_id)
        return {"notebook": nb_meta, "sources": sources, "artifacts": artifacts}

    async def _download_one_source(
        self, notebook_id: str, dest_dir: Path, idx: int, src: dict[str, Any]
    ) -> tuple[Lecture, dict[str, Any] | None]:
        """Download one remote source fulltext and build its Lecture entity.

        Args:
            notebook_id: Remote Gemini Notebook identifier.
            dest_dir: Target local directory under DATA_DIR.
            idx: 1-based lecture sequence number.
            src: Normalized remote source metadata.

        Returns:
            Tuple of (Lecture entity, downloaded metadata dict or None on failure).
        """
        src_id = str(src.get("id", ""))
        title = str(src.get("title") or f"Source {idx}")
        try:
            ft = await self.client.get_source_fulltext(notebook_id, src_id, output_format="markdown")
            path, digest = _write_source_markdown(dest_dir, idx, src, ft)
            lec = Lecture(
                no=idx,
                topic=title,
                filename=path.name,
                sha256=digest,
                source_id=src_id,
                upload_status="ready",
            )
            info = {"id": src_id, "title": title, "path": str(path), "char_count": ft.get("char_count", 0)}
            return lec, info
        except Exception as err:
            logger.warning("Failed to download fulltext for source %s (%s): %s", src_id, title, err)
            return self._placeholder_lecture(idx, title, src_id), None

    async def _download_sources_to_lectures(
        self,
        notebook_id: str,
        dest_dir: Path,
        sources: list[dict[str, Any]],
        selected_ids: set[str] | None,
    ) -> tuple[list[Lecture], list[dict[str, Any]]]:
        """Download selected remote sources as local Markdown files and build Lecture entities.

        Args:
            notebook_id: Remote Gemini Notebook identifier.
            dest_dir: Directory under DATA_DIR where source files are written.
            sources: List of remote source summaries.
            selected_ids: Optional set of source IDs to download (None = all).

        Returns:
            Tuple of (Lecture list, downloaded source summary list).
        """
        lectures: list[Lecture] = []
        downloaded: list[dict[str, Any]] = []
        for idx, src in enumerate(sources, start=1):
            src_id = str(src.get("id", ""))
            title = str(src.get("title") or f"Source {idx}")
            if selected_ids is not None and src_id not in selected_ids:
                lectures.append(self._placeholder_lecture(idx, title, src_id))
                continue
            lec, info = await self._download_one_source(notebook_id, dest_dir, idx, src)
            lectures.append(lec)
            if info is not None:
                downloaded.append(info)
        return lectures, downloaded

    def _placeholder_lecture(self, idx: int, title: str, src_id: str) -> Lecture:
        """Create a placeholder Lecture entry for a skipped remote source.

        Args:
            idx: 1-based lecture sequence number.
            title: Source title.
            src_id: Remote source identifier.

        Returns:
            Lecture entity.
        """
        return Lecture(
            no=idx,
            topic=title,
            filename=title,
            sha256=uuid.uuid4().hex,
            source_id=src_id,
            upload_status="ready",
        )

    def _build_placeholder_lectures(self, remote_sources: list[dict[str, Any]]) -> list[Lecture]:
        """Build Lecture entities without downloading remote source bodies.

        Args:
            remote_sources: List of remote source summaries.

        Returns:
            List of Lecture entities.
        """
        return [
            self._placeholder_lecture(i, str(s.get("title") or f"Source {i}"), str(s.get("id", "")))
            for i, s in enumerate(remote_sources, start=1)
        ]

    async def _resolve_import_target(self, options: ReverseImportOptions) -> tuple[str, str, str, str, Path]:
        """Resolve target course code and name for a remote notebook import.

        Validates `term` and resolves term-scoped `course_no` and `study_dir`.

        Args:
            options: Reverse import configuration options.

        Returns:
            Tuple of `(course_code, course_name, term, course_no, study_dir)`.

        Raises:
            ValueError: When `term` is missing or invalid.
        """
        clean_term = (options.term or "").strip().replace("_", "-")
        if not TERM_PATTERN.match(clean_term):
            raise ValueError(f"term 為必填且須符合學期格式，例如 113-2（收到：{options.term!r}）")
        notebooks = await self.client.list_notebooks()
        nb_meta = next((n for n in notebooks if n["id"] == options.notebook_id), None)
        nb_title = (options.course_name or (nb_meta["title"] if nb_meta else options.notebook_id)).strip()
        existing = self.course_repo.list_courses()
        if options.course_no.strip():
            clean_no = re.sub(r"[^A-Za-z0-9]", "", options.course_no).upper()
        elif options.course_code:
            _, split_no = split_course_code(options.course_code.strip())
            clean_no = re.sub(r"[^A-Za-z0-9]", "", split_no or options.course_code).upper()
        else:
            clean_no = _derive_course_code(nb_title, {c.course_no or c.code for c in existing})
        course_code = make_course_code(clean_term, clean_no)
        folder_name = build_study_folder_name(clean_no, nb_title)
        study_dir = self.study_root / clean_term / folder_name
        ensure_within_roots(study_dir, [self.study_root], "study course directory")
        self.study_layout.ensure_tree(study_dir)
        return course_code, nb_title, clean_term, clean_no, study_dir

    @staticmethod
    def _build_imported_course(
        options: ReverseImportOptions, target: tuple[str, str, str, str, Path], lectures: list[Lecture]
    ) -> Course:
        """Construct the persisted Course entity for a reverse-imported notebook.

        Args:
            options: Reverse import options.
            target: Tuple of `(course_code, nb_title, term, course_no, study_dir)`.
            lectures: Lecture entries built from remote sources.

        Returns:
            Configured `Course` entity.
        """
        course_code, nb_title, term, course_no, study_dir = target
        resolved_dir = str(study_dir.resolve())
        return Course(
            code=course_code,
            name=nb_title,
            source_dir=resolved_dir,
            notebook_id=options.notebook_id,
            profile=ProfileName.RECORD_ONLY if options.record_only else ProfileName.FULL,
            language=options.language,
            watch=False,
            lectures=lectures,
            reuse_notebook=True,
            term=term,
            subject=nb_title,
            study_dir=resolved_dir,
            status=CourseStatus.ARCHIVED if options.record_only else CourseStatus.ACTIVE,
            course_no=course_no,
        )

    async def import_remote_notebook(self, options: ReverseImportOptions) -> dict[str, Any]:
        """Import an existing remote Gemini Notebook as a local course and download files locally.

        Places sources and outputs inside `DATA_DIR/study/<term>/<folder>/`.

        Args:
            options: Reverse import configuration options (including required `term`).

        Returns:
            Summary dictionary with course_code, source_dir, downloaded_sources, and synced_artifacts.
        """
        target = await self._resolve_import_target(options)
        course_code, nb_title, _, _, study_dir = target
        sources_dir = self.study_layout.primary_dir(study_dir, CategoryRole.HANDOUTS)
        remote_sources = await self.client.list_sources(options.notebook_id)
        selected_src_ids = set(options.source_ids) if options.source_ids is not None else None
        if options.download_sources:
            lectures, downloaded_sources = await self._download_sources_to_lectures(
                options.notebook_id, sources_dir, remote_sources, selected_src_ids
            )
        else:
            lectures = self._build_placeholder_lectures(remote_sources)
            downloaded_sources = []
        self.course_repo.save_course(self._build_imported_course(options, target, lectures))
        sync_res = (
            await self.sync_service.sync_course(course_code)
            if options.download_artifacts
            else {"synced_count": 0, "items": []}
        )
        return self._format_download_summary(course_code, downloaded_sources, sync_res, nb_title)

    def _course_sources_dir(self, course_code: str, study_dir: str = "") -> Path:
        """Return local sources folder (`<study_dir>/02 Handouts` or `scratch/unarchived/<code>`).

        Args:
            course_code: Course identifier.
            study_dir: Optional course study directory.

        Returns:
            Destination folder path for downloaded source Markdown files.
        """
        if study_dir:
            return self.study_layout.primary_dir(Path(study_dir), CategoryRole.HANDOUTS)
        return self.scratch_unarchived / course_code

    def _format_download_summary(
        self,
        course_code: str,
        downloaded_sources: list[dict[str, Any]],
        sync_res: dict[str, Any],
        course_name: str | None = None,
    ) -> dict[str, Any]:
        """Build a consistent summary dictionary for import and download-all responses.

        Args:
            course_code: Local course identifier.
            downloaded_sources: List of downloaded source file metadata.
            sync_res: Result dictionary from `RemoteSyncService.sync_course`.
            course_name: Optional course title.

        Returns:
            Normalized summary dictionary.
        """
        course = self.course_repo.get_course(course_code)
        study_dir = course.study_dir if course else ""
        sources_dir = self._course_sources_dir(course_code, study_dir)
        artifacts_dir = resolve_course_output_root(self.output_base_dir / "courses", course_code, study_dir)
        summary: dict[str, Any] = {
            "course_code": course_code,
            "sources_dir": str(sources_dir),
            "artifacts_dir": str(artifacts_dir),
            "downloaded_sources_count": len(downloaded_sources),
            "downloaded_sources": downloaded_sources,
            "synced_artifacts_count": sync_res.get("synced_count", 0),
            "synced_artifacts": sync_res.get("items", []),
        }
        if course_name is not None:
            summary["course_name"] = course_name
        return summary

    async def download_course_files_locally(
        self, course_code: str, include_sources: bool = True, include_artifacts: bool = True
    ) -> dict[str, Any]:
        """Download all remote sources and artifacts for an already-linked course to DATA_DIR.

        Args:
            course_code: Existing local course code.
            include_sources: Whether to download remote source fulltexts as Markdown.
            include_artifacts: Whether to download remote generated artifacts.

        Returns:
            Summary dictionary with downloaded source count, synced artifact count, and local paths.
        """
        course = self.course_repo.get_course(course_code)
        if not course:
            raise ValueError(f"Course not found: {course_code}")
        if not course.notebook_id:
            raise ValueError(f"Course {course_code} has no linked Gemini Notebook")
        sources_dir = self._course_sources_dir(course_code, course.study_dir)
        downloaded_sources: list[dict[str, Any]] = []
        if include_sources:
            remote_sources = await self.client.list_sources(course.notebook_id)
            _, downloaded_sources = await self._download_sources_to_lectures(
                course.notebook_id, sources_dir, remote_sources, None
            )
        sync_res = (
            await self.sync_service.sync_course(course_code)
            if include_artifacts
            else {"synced_count": 0, "items": []}
        )
        return self._format_download_summary(course_code, downloaded_sources, sync_res)

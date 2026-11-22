"""Course source management service: list, upload, and delete Gemini Notebook sources.

Keeps source lifecycle operations separate from `orchestrator.py` and `course_onboarding.py`
so each service module stays concise and focused.
"""

from __future__ import annotations

import base64
import binascii
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from notebooklm_batch_studio.domain.exceptions import CourseNotFoundError
from notebooklm_batch_studio.domain.models import Course, Lecture
from notebooklm_batch_studio.services.job_views import lecture_to_dict

if TYPE_CHECKING:
    from notebooklm_batch_studio.config.settings import AppConfig
    from notebooklm_batch_studio.domain.repositories import (
        CourseRepositoryProtocol,
        NotebookLMClientProtocol,
    )

logger = logging.getLogger(__name__)


def _annotate_sources_and_lectures(
    course: Course, remote_sources: list[dict[str, Any]], remote_error: str | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Cross-reference remote Gemini Notebook sources with registered local lectures.

    Args:
        course: Course domain entity.
        remote_sources: Normalized remote source dictionaries from Gemini Notebook.
        remote_error: Optional error message when remote listing failed.

    Returns:
        Tuple of `(annotated_sources, annotated_lectures)`.
    """
    by_id = {lec.source_id: lec for lec in course.lectures if lec.source_id}
    by_title = {lec.filename: lec for lec in course.lectures}
    remote_ids = {str(src["id"]) for src in remote_sources if src.get("id")}

    annotated_sources: list[dict[str, Any]] = []
    for src in remote_sources:
        lec = by_id.get(str(src.get("id"))) or by_title.get(str(src.get("title")))
        annotated_sources.append(
            {
                **src,
                "lecture_no": lec.no if lec else None,
                "lecture_topic": lec.topic if lec else None,
            }
        )

    lectures_out: list[dict[str, Any]] = []
    for lec in course.lectures:
        row = lecture_to_dict(lec)
        row["in_notebook"] = bool(lec.source_id and (remote_error is not None or lec.source_id in remote_ids))
        lectures_out.append(row)
    return annotated_sources, lectures_out


class CourseSourceMixin:
    """Mixin providing listing, upload, and deletion of Gemini Notebook sources for a course."""

    if TYPE_CHECKING:
        course_repo: CourseRepositoryProtocol
        notebooklm_client: NotebookLMClientProtocol
        config: AppConfig

        async def _ensure_notebook_id(self, course: Course) -> tuple[str, dict[str, str]]:
            """Resolve or create the Gemini Notebook ID for a course.

            Args:
                course: Domain Course entity.

            Returns:
                Tuple of `(notebook_id, existing_ready_sources)`.
            """
            ...

        async def _check_source_limit(self, course: Course) -> None:
            """Check whether course lecture count fits within account source limit.

            Args:
                course: Domain Course entity.
            """
            ...

        async def _perform_lecture_upload(
            self, course_code: str, notebook_id: str, lec: Lecture, pdf_file: Path
        ) -> None:
            """Upload one local PDF file and wait until ready.

            Args:
                course_code: Course identifier.
                notebook_id: Notebook identifier.
                lec: Target Lecture entity.
                pdf_file: Path to the local PDF file.
            """
            ...

        async def _upload_single_lecture(
            self,
            course: Course,
            notebook_id: str,
            lec: Lecture,
            existing_sources: dict[str, str],
        ) -> None:
            """Upload a single lecture PDF or reuse an existing ready source.

            Args:
                course: Domain Course entity.
                notebook_id: Notebook identifier.
                lec: Target Lecture entity.
                existing_sources: Mapping of source title to source id.
            """
            ...

    def _require_course(self, course_code: str) -> Course:
        """Load a registered course or raise CourseNotFoundError.

        Args:
            course_code: Course identifier.

        Returns:
            Domain Course entity.

        Raises:
            CourseNotFoundError: When the course is not registered.
        """
        course = self.course_repo.get_course(course_code)
        if course is None:
            raise CourseNotFoundError(f"Course not found: {course_code}")
        return course

    def _reconcile_course_sources(self, course: Course, remote_sources: list[dict[str, Any]]) -> Course:
        """Sync local lecture source_ids against the live remote source list.

        Args:
            course: Registered Course entity.
            remote_sources: Sources currently present in Gemini Notebook.

        Returns:
            Refreshed Course entity after reconciliation.
        """
        remote_ids = {str(s["id"]) for s in remote_sources if s.get("id")}
        ready_by_title = {
            str(s["title"]): str(s["id"])
            for s in remote_sources
            if s.get("title") and s.get("status") == "ready"
        }
        changed = False
        for lec in course.lectures:
            changed = self._reconcile_one_lecture(course.code, lec, remote_ids, ready_by_title) or changed
        return self._require_course(course.code) if changed else course

    def _reconcile_one_lecture(
        self,
        course_code: str,
        lec: Lecture,
        remote_ids: set[str],
        ready_by_title: dict[str, str],
    ) -> bool:
        """Reconcile one lecture's source link against remote IDs and ready titles.

        Args:
            course_code: Course identifier.
            lec: Lecture entity.
            remote_ids: Set of remote source IDs present in the notebook.
            ready_by_title: Mapping of ready remote source titles to IDs.

        Returns:
            True if the local lecture record was updated.
        """
        matched_id = ready_by_title.get(lec.filename)
        if lec.source_id and lec.source_id not in remote_ids:
            if matched_id:
                self.course_repo.update_lecture_upload_status(
                    course_code, lec.no, "ready", source_id=matched_id, error_message=None
                )
            else:
                self.course_repo.update_lecture_upload_status(
                    course_code, lec.no, "pending", source_id=None, error_message=None
                )
            return True
        if (not lec.source_id or lec.upload_status != "ready") and matched_id:
            self.course_repo.update_lecture_upload_status(
                course_code, lec.no, "ready", source_id=matched_id, error_message=None
            )
            return True
        return False

    async def list_course_sources(self, course_code: str) -> dict[str, Any]:
        """List remote Gemini Notebook sources and local lecture sync state for a course.

        Args:
            course_code: Course identifier.

        Returns:
            Dictionary containing course metadata, remote sources, local lectures, and any remote error.

        Raises:
            CourseNotFoundError: When the course is not registered.
        """
        course = self._require_course(course_code)
        remote_sources: list[dict[str, Any]] = []
        remote_error: str | None = None
        if course.notebook_id:
            try:
                remote_sources = await self.notebooklm_client.list_sources(course.notebook_id)
                course = self._reconcile_course_sources(course, remote_sources)
            except Exception as err:
                logger.warning("Failed to list sources for %s (%s): %s", course_code, course.notebook_id, err)
                remote_error = str(err)

        sources_out, lectures_out = _annotate_sources_and_lectures(course, remote_sources, remote_error)
        notebook_url = (
            f"https://notebook.google.com/notebook/{course.notebook_id}" if course.notebook_id else None
        )
        return {
            "code": course.code,
            "name": course.name,
            "notebook_id": course.notebook_id,
            "notebook_url": notebook_url,
            "source_dir": course.source_dir,
            "sources": sources_out,
            "lectures": lectures_out,
            "remote_error": remote_error,
        }

    def _resolve_lecture_and_pdf(self, course: Course, lecture_no: int) -> tuple[Lecture, Path]:
        """Find a course lecture and verify that its local PDF exists.

        Args:
            course: Domain Course entity.
            lecture_no: Sequence number of the lecture.

        Returns:
            Tuple of `(Lecture, Path)` pointing to the readable local PDF.

        Raises:
            ValueError: When `lecture_no` does not belong to `course`.
            FileNotFoundError: When the local lecture PDF does not exist.
        """
        lec = next((item for item in course.lectures if item.no == lecture_no), None)
        if lec is None:
            raise ValueError(f"Lecture {lecture_no} not found in course {course.code}")
        rel = lec.relative_path or lec.filename
        pdf_file = Path(course.source_dir) / rel
        if not pdf_file.exists():
            pdf_file = Path(course.source_dir) / lec.filename
        if not pdf_file.exists():
            self.course_repo.update_lecture_upload_status(
                course.code, lec.no, "failed", error_message=f"File not found: {lec.filename}"
            )
            raise FileNotFoundError(f"Lecture PDF not found: {pdf_file}")
        return lec, pdf_file

    async def upload_lecture_source(
        self, course_code: str, lecture_no: int, force: bool = False
    ) -> dict[str, Any]:
        """Upload or re-upload a specific course lecture PDF to Gemini Notebook.

        Args:
            course_code: Course identifier.
            lecture_no: Sequence number of the lecture.
            force: When True, always upload the local PDF even if a source ID is recorded.

        Returns:
            Upload result dictionary with `code`, `notebook_id`, `no`, `upload_status`, and `source_id`.
        """
        course = self._require_course(course_code)
        lec, pdf_file = self._resolve_lecture_and_pdf(course, lecture_no)
        await self._check_source_limit(course)
        notebook_id, existing_sources = await self._ensure_notebook_id(course)

        if force:
            await self._perform_lecture_upload(course.code, notebook_id, lec, pdf_file)
        else:
            await self._upload_single_lecture(course, notebook_id, lec, existing_sources)

        updated = next(
            (item for item in self._require_course(course_code).lectures if item.no == lecture_no),
            lec,
        )
        return {
            "code": course_code,
            "notebook_id": notebook_id,
            "no": lecture_no,
            "filename": updated.filename,
            "upload_status": updated.upload_status,
            "source_id": updated.source_id,
            "error_message": updated.error_message,
        }

    def _resolve_upload_file_path(self, raw_path: str) -> Path:
        """Validate a local PDF file path inside allowed filesystem roots.

        Args:
            raw_path: User-supplied filesystem path string.

        Returns:
            Resolved Path pointing to an existing `.pdf` file.

        Raises:
            ValueError: When path is outside allowed roots or not a `.pdf`.
            FileNotFoundError: When the target file does not exist.
        """
        candidate = Path(raw_path).expanduser().resolve()
        allowed_roots = (Path.home().resolve(), self.config.data_dir.resolve())
        if not any(candidate.is_relative_to(root) for root in allowed_roots):
            raise ValueError("file_path must be inside the home directory or DATA_DIR")
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f"PDF file not found: {raw_path}")
        if candidate.suffix.lower() != ".pdf":
            raise ValueError("Only .pdf files can be uploaded as sources")
        return candidate

    def _save_uploaded_base64_pdf(self, course_code: str, filename: str, content_base64: str) -> Path:
        """Decode and store a browser-uploaded PDF under DATA_DIR without modifying course source_dir.

        Args:
            course_code: Course identifier.
            filename: Original uploaded filename.
            content_base64: Base64-encoded (or data-URI) PDF payload.

        Returns:
            Path to the written PDF file under `courses_input_dir/<course_code>/_uploaded_sources/`.

        Raises:
            ValueError: When filename is invalid, base64 is malformed, or content is not a PDF.
        """
        safe_name = Path(str(filename)).name.strip()
        if not safe_name or safe_name.startswith(".") or not safe_name.lower().endswith(".pdf"):
            raise ValueError("filename must be a valid .pdf filename")

        raw_b64 = content_base64.strip()
        if raw_b64.startswith("data:") and "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        try:
            data = base64.b64decode(raw_b64, validate=True)
        except (binascii.Error, ValueError) as err:
            raise ValueError("Invalid base64 PDF content") from err
        if not data.startswith(b"%PDF"):
            raise ValueError("Uploaded file is not a valid PDF document")

        dest_dir = self.config.courses_input_dir / course_code / "_uploaded_sources"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / safe_name
        dest_path.write_bytes(data)
        return dest_path

    def _resolve_payload_pdf_path(self, course: Course, payload: dict[str, Any]) -> Path:
        """Select and validate the PDF file path from an upload payload.

        Args:
            course: Target Course entity.
            payload: Keyword upload fields (`file_path`, `filename`, `content_base64`).

        Returns:
            Resolved Path to the PDF file ready for upload.

        Raises:
            ValueError: When no valid upload source fields were provided.
        """
        if payload.get("file_path"):
            return self._resolve_upload_file_path(str(payload["file_path"]))
        if payload.get("filename") and payload.get("content_base64"):
            return self._save_uploaded_base64_pdf(
                course.code, str(payload["filename"]), str(payload["content_base64"])
            )
        raise ValueError("Provide lecture_no, file_path, or filename with content_base64")

    async def upload_custom_source(self, course_code: str, **payload: Any) -> dict[str, Any]:
        """Upload a lecture PDF, local PDF file, or browser-uploaded PDF to a course's notebook.

        Args:
            course_code: Course identifier.
            **payload: Upload fields (`lecture_no`, `file_path`, `filename`, `content_base64`).

        Returns:
            Dictionary describing the uploaded Gemini Notebook source.

        Raises:
            CourseNotFoundError: When the course is not registered.
            ValueError: When upload inputs are missing or invalid.
            FileNotFoundError: When a specified local file does not exist.
        """
        course = self._require_course(course_code)
        if payload.get("lecture_no") is not None:
            return await self.upload_lecture_source(course_code, int(payload["lecture_no"]), force=True)

        pdf_path = self._resolve_payload_pdf_path(course, payload)
        notebook_id, _ = await self._ensure_notebook_id(course)
        source_id = await self.notebooklm_client.upload_source(notebook_id, str(pdf_path))
        await self.notebooklm_client.wait_source_ready(notebook_id, source_id)
        for lec in course.lectures:
            if lec.filename == pdf_path.name:
                self.course_repo.update_lecture_upload_status(
                    course.code, lec.no, "ready", source_id=source_id, error_message=None
                )
        logger.info("Uploaded source %s (%s) to notebook %s", pdf_path.name, source_id, notebook_id)
        return {
            "code": course_code,
            "notebook_id": notebook_id,
            "source_id": source_id,
            "filename": pdf_path.name,
            "status": "ready",
        }

    def _unlink_deleted_source_lectures(self, course: Course, clean_id: str) -> list[int]:
        """Reset local lectures linked to a deleted Gemini Notebook source back to pending.

        Args:
            course: Domain Course entity.
            clean_id: Deleted remote source identifier.

        Returns:
            Sorted list of unlinked lecture sequence numbers.
        """
        unlinked: list[int] = []
        for lec in course.lectures:
            if lec.source_id == clean_id:
                self.course_repo.update_lecture_upload_status(
                    course.code, lec.no, "pending", source_id=None, error_message=None
                )
                unlinked.append(lec.no)
        return unlinked

    async def delete_course_source(self, course_code: str, source_id: str) -> dict[str, Any]:
        """Delete a source from the course's Gemini Notebook and unlink matching local lectures.

        Args:
            course_code: Course identifier.
            source_id: Remote Gemini Notebook source identifier.

        Returns:
            Dictionary confirming deletion and listing any unlinked lecture numbers.
        """
        course = self._require_course(course_code)
        clean_id = source_id.strip()
        if not clean_id:
            raise ValueError("source_id must not be empty")
        if not course.notebook_id:
            raise ValueError(f"Course {course_code} has no linked Gemini Notebook")

        await self.notebooklm_client.delete_source(course.notebook_id, clean_id)
        unlinked = self._unlink_deleted_source_lectures(course, clean_id)
        logger.info(
            "Deleted source %s from course %s (%s); unlinked lectures=%s",
            clean_id,
            course_code,
            course.notebook_id,
            unlinked,
        )
        return {
            "code": course_code,
            "notebook_id": course.notebook_id,
            "deleted_source_id": clean_id,
            "unlinked_lectures": unlinked,
        }

"""Service for advanced remote Gemini Notebook artifact operations (cinematic video, slide, export)."""

from __future__ import annotations

import logging
from typing import Any

from notebooklm_batch_studio.domain.models import Course
from notebooklm_batch_studio.domain.notebooklm_protocol import NotebookLMClientProtocol
from notebooklm_batch_studio.domain.repositories import CourseRepositoryProtocol

logger = logging.getLogger(__name__)


class RemoteAdminService:
    """Coordinates advanced remote artifact actions on a course's Gemini Notebook."""

    def __init__(self, course_repo: CourseRepositoryProtocol, client: NotebookLMClientProtocol) -> None:
        """Initialize service with course repository and NotebookLM client.

        Args:
            course_repo: Course persistence repository.
            client: NotebookLM client protocol implementation.
        """
        self.course_repo = course_repo
        self.client = client

    def _require_notebook(self, course_code: str) -> tuple[Course, str]:
        """Resolve course and verify it has a linked Gemini Notebook.

        Args:
            course_code: Course identifier.

        Returns:
            Tuple of (Course, notebook_id).

        Raises:
            ValueError: If course is missing or has no notebook_id.
        """
        course = self.course_repo.get_course(course_code)
        if not course:
            raise ValueError(f"Course not found: {course_code}")
        if not course.notebook_id:
            raise ValueError(f"Course {course_code} has no linked Gemini Notebook notebook")
        return course, course.notebook_id

    async def generate_cinematic_video(
        self, course_code: str, instructions: str, lecture_no: int | None = None
    ) -> dict[str, Any]:
        """Generate a cinematic video overview for a course or single lecture.

        Args:
            course_code: Course identifier.
            instructions: Focus prompt instructions.
            lecture_no: Optional lecture number to scope source_ids.

        Returns:
            Summary dictionary with generated artifact_id.
        """
        course, nb_id = self._require_notebook(course_code)
        source_ids: list[str] | None = None
        if lecture_no is not None:
            source_ids = [lec.source_id for lec in course.lectures if lec.no == lecture_no and lec.source_id]
        art_id = await self.client.generate_cinematic_video(
            nb_id, instructions=instructions, source_ids=source_ids, language=course.language
        )
        logger.info("Generated cinematic video %s for %s", art_id, course_code)
        return {"course_code": course_code, "artifact_id": art_id, "kind": "cinematic_video"}

    async def revise_slide(
        self, course_code: str, artifact_id: str, slide_index: int, prompt: str
    ) -> dict[str, Any]:
        """Revise a single slide in an existing slide deck artifact.

        Args:
            course_code: Course identifier.
            artifact_id: Slide deck artifact identifier.
            slide_index: Zero-based slide index.
            prompt: Revision instructions.

        Returns:
            Summary dictionary with revised artifact_id.
        """
        _, nb_id = self._require_notebook(course_code)
        updated_id = await self.client.revise_slide(nb_id, artifact_id, slide_index, prompt)
        logger.info("Revised slide %d of artifact %s for %s", slide_index, artifact_id, course_code)
        return {"course_code": course_code, "artifact_id": updated_id, "slide_index": slide_index}

    async def export_artifact(
        self, course_code: str, artifact_id: str, title: str = "Export", kind: str = "report"
    ) -> dict[str, Any]:
        """Export a remote report or data table to Google Docs or Sheets.

        Args:
            course_code: Course identifier.
            artifact_id: Remote artifact identifier.
            title: Exported document title.
            kind: Artifact kind ('report' or 'data_table').

        Returns:
            Export metadata dictionary.
        """
        _, nb_id = self._require_notebook(course_code)
        return await self.client.export_artifact(nb_id, artifact_id, title=title, kind=kind)

    async def suggest_reports(self, course_code: str) -> dict[str, Any]:
        """Fetch AI-suggested report topics for a course's Gemini Notebook.

        Args:
            course_code: Course identifier.

        Returns:
            Dictionary with course_code and suggestions list.
        """
        _, nb_id = self._require_notebook(course_code)
        suggestions = await self.client.suggest_reports(nb_id)
        return {"course_code": course_code, "suggestions": suggestions}

    async def retry_remote_artifact(self, course_code: str, artifact_id: str) -> dict[str, Any]:
        """Retry a failed remote artifact directly on Gemini Notebook.

        Args:
            course_code: Course identifier.
            artifact_id: Failed remote artifact identifier.

        Returns:
            Retry status dictionary.
        """
        _, nb_id = self._require_notebook(course_code)
        return await self.client.retry_remote_artifact(nb_id, artifact_id)

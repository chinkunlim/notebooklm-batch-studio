"""Protocol for the Gemini Notebook client: what services may ask Gemini Notebook to do.

Split out of `repositories.py` to keep that file within the size limit; import it from either
module.
"""

from __future__ import annotations

from typing import Any, Protocol

from notebooklm_batch_studio.domain.models import GenerationOptions


class NotebookLMClientProtocol(Protocol):
    """Abstract interface for Google Gemini Notebook operations and artifact generation.

    Every `generate_*` waits for completion and returns the artifact id; callers pass that id
    to the matching `download_*` and to `rename_artifact`. Refs: ADR-004
    """

    def check_auth(self) -> bool:
        """Check whether local authentication session is valid.

        Returns:
            True if session is valid and active, False otherwise.
        """
        ...

    async def ask(self, notebook_id: str, question: str, source_ids: list[str] | None = None) -> str:
        """Ask the notebook a question grounded in its sources.

        Args:
            notebook_id: Notebook identifier.
            question: Question text.
            source_ids: Limit to these sources (None = all).

        Returns:
            Answer text.
        """
        ...

    async def find_notebook_by_title(self, title: str) -> str | None:
        """Find an existing notebook whose title matches exactly.

        Args:
            title: Notebook title.

        Returns:
            Notebook id, or None.
        """
        ...

    async def list_ready_sources(self, notebook_id: str) -> dict[str, str]:
        """Map ready source titles (PDF file names) to source ids.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            Title to id.
        """
        ...

    async def create_notebook(self, title: str) -> str:
        """Create a new notebook in Gemini Notebook.

        Args:
            title: The title of the new notebook.

        Returns:
            The created notebook identifier string.
        """
        ...

    async def upload_source(self, notebook_id: str, file_path: str) -> str:
        """Upload a PDF source file to a notebook.

        Args:
            notebook_id: The notebook identifier.
            file_path: Filesystem path to the local PDF file.

        Returns:
            The uploaded source identifier string.
        """
        ...

    async def wait_source_ready(self, notebook_id: str, source_id: str, timeout_seconds: int = 180) -> None:
        """Wait until an uploaded source is fully indexed and ready for generation.

        Args:
            notebook_id: The notebook identifier.
            source_id: The source identifier.
            timeout_seconds: Maximum time to wait in seconds.
        """
        ...

    async def get_source_limit(self) -> int | None:
        """Return the maximum number of sources allowed per notebook.

        Returns:
            Source limit, or None when unknown.
        """
        ...

    async def get_quota_status(self) -> dict[str, Any]:
        """Return the live usage meter and account limits.

        Returns:
            JSON-friendly quota summary.
        """
        ...

    async def generate_quiz(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        difficulty: str | None = None,
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate a quiz from selected sources and wait for completion.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for the quiz generation.
            difficulty: 'easy', 'medium', 'hard', or None for the default.
            options: Course generation options (None = defaults).

        Returns:
            The completed quiz artifact id.
        """
        ...

    async def download_quiz(self, notebook_id: str, output_path: str, artifact_id: str | None = None) -> None:
        """Download generated quiz JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_flashcards(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        options: GenerationOptions | None = None,
    ) -> str:
        """Request generation of flashcards from selected sources.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for flashcards generation.
            options: Course generation options (None = defaults).

        Returns:
            The completed flashcards artifact id.
        """
        ...

    async def download_flashcards(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download generated flashcards JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_mind_map(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Generate a mind map from selected sources.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional instructional prompt for mind map generation.
            language: Course language ('zh-TW', 'en', 'bilingual').

        Returns:
            The mind map note id (pass it to download_mind_map).
        """
        ...

    async def download_mind_map(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download generated mind map JSON to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_audio(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate a Deep Dive audio overview and wait for completion.

        Args:
            notebook_id: The notebook identifier.
            source_ids: List of source identifiers to generate from.
            prompt: Optional customization prompt for audio discussion.
            language: Course language ('zh-TW', 'en', 'bilingual').
            options: Course generation options (None = defaults).

        Returns:
            The completed audio artifact id.
        """
        ...

    async def download_audio(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download generated Audio MP3 file to local storage.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where MP3 should be saved.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def rename_artifact(self, notebook_id: str, artifact_id: str, title: str) -> None:
        """Rename an artifact within Gemini Notebook for readability.

        Args:
            notebook_id: The notebook identifier.
            artifact_id: The artifact identifier to rename.
            title: The new title string (e.g. '[03] Quiz 1-基礎').
        """
        ...

    async def rename_mind_map(self, notebook_id: str, note_id: str, title: str) -> None:
        """Rename a note-backed mind map within Gemini Notebook. Refs: ISSUE-011

        Args:
            notebook_id: The notebook identifier.
            note_id: The mind map note identifier.
            title: The new title string.
        """
        ...

    async def generate_report(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        report_format: str = "briefing_doc",
    ) -> str:
        """Request generation of a study guide or briefing report.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language ('zh-TW', 'en', 'bilingual').
            report_format: Format key (briefing_doc, study_guide, blog_post).

        Returns:
            Task or artifact identifier.
        """
        ...

    async def download_report(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download report/study guide content to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_slide_deck(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Request generation of slide deck presentation outline.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.
            options: Course generation options (None = defaults).

        Returns:
            Task or artifact identifier.
        """
        ...

    async def download_slide_deck(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None, output_format: str = "pdf"
    ) -> None:
        """Download a slide deck as PDF or PPTX.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
            output_format: 'pdf' or 'pptx'.
        """
        ...

    async def generate_infographic(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Request generation of an infographic.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.
            options: Course generation options (None = defaults).

        Returns:
            Task or artifact identifier.
        """
        ...

    async def download_infographic(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download infographic to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_data_table(
        self, notebook_id: str, source_ids: list[str], prompt: str | None = None, language: str = "zh-TW"
    ) -> str:
        """Request generation of comparison data table.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.

        Returns:
            Task or artifact identifier.
        """
        ...

    async def download_data_table(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download data table content to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def generate_video(
        self,
        notebook_id: str,
        source_ids: list[str],
        prompt: str | None = None,
        language: str = "zh-TW",
        options: GenerationOptions | None = None,
    ) -> str:
        """Request generation of cinematic video overview.

        Args:
            notebook_id: The notebook identifier.
            source_ids: Selected source identifiers.
            prompt: Optional custom instructions.
            language: Target language.
            options: Course generation options (None = defaults).

        Returns:
            Task or artifact identifier.
        """
        ...

    async def download_video(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download generated video to a local file.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Optional artifact identifier.
        """
        ...

    async def list_artifacts(self, notebook_id: str) -> list[dict[str, Any]]:
        """List all remote artifacts present in a notebook.

        Args:
            notebook_id: Notebook identifier.

        Returns:
            List of dictionary summaries of artifacts.
        """
        ...

    async def download_artifact_by_kind(
        self, notebook_id: str, artifact_id: str, kind: str, output_path: str
    ) -> str:
        """Download remote artifact using the method matching its kind.

        Args:
            notebook_id: Notebook identifier.
            artifact_id: Artifact identifier.
            kind: Artifact kind string.
            output_path: Target path.

        Returns:
            Target output path string.
        """
        ...

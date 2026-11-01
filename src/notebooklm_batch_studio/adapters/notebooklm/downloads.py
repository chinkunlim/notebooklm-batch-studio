"""Per-kind download helpers for the NotebookLM adapter.

Each method downloads exactly one artifact by id through `download_artifact`, which the adapter
implements (with error translation). Split out of `client.py` to keep that file under the size
limit.
"""

from __future__ import annotations

from typing import Any


class ArtifactDownloadsMixin:
    """`download_<kind>` methods implemented on top of `self.download_artifact`."""

    async def download_artifact(
        self, kind: str, notebook_id: str, output_path: str, artifact_id: str, **extra: Any
    ) -> None:
        """Download one artifact; implemented by the adapter.

        Args:
            kind: Downloader suffix.
            notebook_id: The notebook identifier.
            output_path: Local filesystem destination.
            artifact_id: Artifact (or mind map note) id.
            **extra: Extra downloader keywords.

        Raises:
            NotImplementedError: Always; the concrete adapter overrides this.
        """
        raise NotImplementedError

    async def download_quiz(self, notebook_id: str, output_path: str, artifact_id: str | None = None) -> None:
        """Download a quiz JSON.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Artifact id returned by generate_quiz.
        """
        await self.download_artifact("quiz", notebook_id, output_path, artifact_id or "")

    async def download_flashcards(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download a flashcards JSON.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Artifact id returned by generate_flashcards.
        """
        await self.download_artifact("flashcards", notebook_id, output_path, artifact_id or "")

    async def download_mind_map(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download a mind map JSON.

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where JSON should be saved.
            artifact_id: Mind map note id returned by generate_mind_map.
        """
        await self.download_artifact("mind_map", notebook_id, output_path, artifact_id or "")

    async def download_audio(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download an audio overview (MP3/MP4 audio).

        Args:
            notebook_id: The notebook identifier.
            output_path: Local filesystem path where audio should be saved.
            artifact_id: Artifact id returned by generate_audio.
        """
        await self.download_artifact("audio", notebook_id, output_path, artifact_id or "")

    async def download_report(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download a report / study guide as Markdown.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Artifact id returned by generate_report.
        """
        await self.download_artifact("report", notebook_id, output_path, artifact_id or "")

    async def download_slide_deck(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None, output_format: str = "pdf"
    ) -> None:
        """Download a slide deck as PDF or PPTX.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Artifact id returned by generate_slide_deck.
            output_format: 'pdf' or 'pptx'.
        """
        await self.download_artifact(
            "slide_deck", notebook_id, output_path, artifact_id or "", output_format=output_format
        )

    async def download_infographic(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download an infographic image.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Artifact id returned by generate_infographic.
        """
        await self.download_artifact("infographic", notebook_id, output_path, artifact_id or "")

    async def download_data_table(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download a data table.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Artifact id returned by generate_data_table.
        """
        await self.download_artifact("data_table", notebook_id, output_path, artifact_id or "")

    async def download_video(
        self, notebook_id: str, output_path: str, artifact_id: str | None = None
    ) -> None:
        """Download a video overview.

        Args:
            notebook_id: The notebook identifier.
            output_path: Target filesystem destination.
            artifact_id: Artifact id returned by generate_video.
        """
        await self.download_artifact("video", notebook_id, output_path, artifact_id or "")

"""Phase 1 modular Markdown note generation services (Refs: ADR-012)."""

from notebooklm_batch_studio.services.notes.note_pipeline_service import (
    ChapterNoteRequest,
    NotePipelineService,
)

__all__ = ["ChapterNoteRequest", "NotePipelineService"]

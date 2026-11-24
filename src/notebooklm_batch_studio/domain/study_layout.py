"""Domain re-export of study folder category definitions and layout helpers (Refs: ADR-014)."""

from __future__ import annotations

import logging

from notebooklm_batch_studio.config.study_layout import (
    DEFAULT_LAYOUT,
    CategoryRole,
    StudyLayout,
    layout_from_names,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CategoryRole",
    "DEFAULT_LAYOUT",
    "StudyLayout",
    "layout_from_names",
]

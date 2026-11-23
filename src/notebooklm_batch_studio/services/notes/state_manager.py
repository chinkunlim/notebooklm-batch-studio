"""Atomic state and cross-process pause persistence for note generation (Refs: ADR-012).

Stores per-course chapter generation state under `DATA_DIR/state/notes/`
using atomic temp-file replacement so Web UI, HTTP, and MCP stay synchronized.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _safe_key(name: str) -> str:
    """Sanitize a course key into a filesystem-safe filename stem.

    Args:
        name: Raw course identifier or code.

    Returns:
        Safe filename stem.
    """
    cleaned = re.sub(r"[^\w\-.]+", "_", name.strip())
    return cleaned or "default"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically via a temporary file in the same directory.

    Args:
        path: Target JSON file path.
        payload: Serializable dictionary.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class NoteStateManager:
    """Manages per-course chapter state and pause flags under `DATA_DIR/state/notes/`."""

    def __init__(self, state_root: Path) -> None:
        """Initialize the state manager.

        Args:
            state_root: Root directory (typically `<data_dir>/state/notes`).
        """
        self.state_root = state_root
        self.state_root.mkdir(parents=True, exist_ok=True)

    def _state_path(self, course_key: str) -> Path:
        """Return JSON state file path for a course.

        Args:
            course_key: Course identifier.

        Returns:
            Path to `<course_key>.json`.
        """
        return self.state_root / f"{_safe_key(course_key)}.json"

    def _pause_path(self, course_key: str) -> Path:
        """Return cross-process pause request file path for a course.

        Args:
            course_key: Course identifier.

        Returns:
            Path to `<course_key>.pause.json`.
        """
        return self.state_root / f"{_safe_key(course_key)}.pause.json"

    def load_course_state(self, course_key: str) -> dict[str, Any]:
        """Load persisted note generation state for a course.

        Args:
            course_key: Course identifier.

        Returns:
            Dictionary with `course_key`, `chapters`, and `updated_at`.
        """
        path = self._state_path(course_key)
        if not path.is_file():
            return {"course_key": course_key, "chapters": {}, "updated_at": None}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("chapters", {})
                return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read note state %s: %s", path, exc)
        return {"course_key": course_key, "chapters": {}, "updated_at": None}

    def update_chapter_state(
        self,
        course_key: str,
        chapter_id: str,
        chapter_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Atomically update one chapter's state entry for a course.

        Args:
            course_key: Course identifier.
            chapter_id: Chapter identifier (e.g. `ch01`).
            chapter_state: Updated chapter state fields.

        Returns:
            Full updated course state dictionary.
        """
        state = self.load_course_state(course_key)
        chapters = state.setdefault("chapters", {})
        chapters[chapter_id] = {
            **chapters.get(chapter_id, {}),
            **chapter_state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write_json(self._state_path(course_key), state)
        return state

    def request_pause(self, course_key: str) -> None:
        """Persist a cross-process pause request for a course.

        Args:
            course_key: Course identifier.
        """
        _atomic_write_json(
            self._pause_path(course_key),
            {"paused": True, "requested_at": datetime.now(timezone.utc).isoformat()},
        )
        logger.info("Requested pause for note generation course=%s", course_key)

    def clear_pause(self, course_key: str) -> None:
        """Remove any pending pause request for a course.

        Args:
            course_key: Course identifier.
        """
        path = self._pause_path(course_key)
        if path.is_file():
            path.unlink()
            logger.info("Cleared pause request for course=%s", course_key)

    def is_pause_requested(self, course_key: str) -> bool:
        """Check whether a pause request is currently active for a course.

        Args:
            course_key: Course identifier.

        Returns:
            True if a pause file exists.
        """
        return self._pause_path(course_key).is_file()
